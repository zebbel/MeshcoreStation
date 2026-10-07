"""Fixed-repository updater. All subprocesses use argument arrays, never a shell."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.updates'
REMOTE = 'https://github.com/zebbel/MeshcoreStation.git'
SERVICE = 'meshcorestation.service'
ACTIVE = {'queued', 'preparing', 'backing_up', 'installing', 'verifying', 'rolling_back'}


def run(*args, timeout=120):
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed:\n{result.stdout[-2000:]}')
    return result.stdout.strip()


def write(name, value):
    STATE.mkdir(mode=0o700, exist_ok=True)
    temporary = STATE / (name + '.tmp')
    temporary.write_text(json.dumps(value))
    os.chmod(temporary, 0o600)
    temporary.replace(STATE / name)


def read(name):
    try:
        return json.loads((STATE / name).read_text())
    except FileNotFoundError:
        return {}


@contextlib.contextmanager
def lock():
    STATE.mkdir(mode=0o700, exist_ok=True)
    with (STATE / 'lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('An update operation is already running.') from None
        yield


def local_revision():
    return run('git', 'rev-parse', 'HEAD')


def validate_checkout():
    if run('git', 'rev-parse', '--show-toplevel') != str(ROOT):
        raise RuntimeError('Install from a Git clone to use web updates.')
    if run('git', 'symbolic-ref', '--short', 'HEAD') != 'main':
        raise RuntimeError('Web updates require the main branch.')
    if run('git', 'status', '--porcelain', '--untracked-files=normal'):
        raise RuntimeError('Local source changes must be committed or removed before updating.')
    remote = run('git', 'remote', 'get-url', 'origin').removesuffix('.git').lower()
    if remote != REMOTE.removesuffix('.git').lower():
        raise RuntimeError('Web updates require the zebbel/MeshcoreStation HTTPS origin.')


def ready():
    try:
        return run('systemctl', 'is-active', 'meshcorestation-update.path', timeout=5) == 'active'
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return False


def check():
    with lock():
        validate_checkout()
        run('git', 'fetch', '--no-tags', REMOTE, 'refs/heads/main')
        current, latest = local_revision(), run('git', 'rev-parse', 'FETCH_HEAD')
        run('git', 'merge-base', '--is-ancestor', current, latest)
        source = run('git', 'show', f'{latest}:meshcorestation/__init__.py')
        match = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)', source)
        result = {'current': current, 'latest': latest, 'available': current != latest,
                  'latest_version': match.group(1) if match else latest[:8],
                  'checked_at': int(time.time()), 'ready': ready(),
                  'changes_url': f'https://github.com/zebbel/MeshcoreStation/compare/{current}...{latest}'}
        write('check.json', result)
        return result


def queue(target):
    with lock():
        checked = read('check.json')
        if not ready():
            raise RuntimeError('Run the one-time terminal update to install the web update service.')
        if read('status.json').get('phase') in ACTIVE or (STATE / 'request.json').exists() or read('transaction.json'):
            raise RuntimeError('An update is already queued or running.')
        validate_checkout()
        if not re.fullmatch('[0-9a-f]{40}', str(target)) or target != checked.get('latest') or not checked.get('available'):
            raise RuntimeError('Check for updates again before installing.')
        if local_revision() != checked['current']:
            raise RuntimeError('The installed code changed. Check for updates again.')
        write('status.json', {'phase': 'queued', 'message': 'Update queued. Preparing backup…', 'target': target})
        write('request.json', {'target': target, 'current': checked['current']})


def service(action):
    run('sudo', '-n', '/usr/bin/systemctl', action, SERVICE, timeout=90)


def healthy(target, port):
    deadline = time.monotonic() + 90
    successes = 0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/update/health', timeout=3) as response:
                if json.load(response).get('revision') == target:
                    successes += 1
                    if successes >= 3:
                        return
                else:
                    successes = 0
        except (OSError, ValueError):
            successes = 0
        time.sleep(2)
    raise RuntimeError('The updated dashboard did not become healthy within 90 seconds.')


def check_dependencies(python):
    try:
        run(python, '-m', 'pip', 'check')
    except RuntimeError as exc:
        # Preserve the installer's recovery for incompatible Pi native wheels.
        names = re.findall(r'^(dbus-fast|pycryptodome|markupsafe) (\S+) is not supported on this platform\s*$', str(exc), re.M | re.I)
        if not names:
            raise
        run(python, '-m', 'pip', 'install', '--force-reinstall', '--no-deps', '--no-cache-dir',
            '--no-binary=dbus-fast,pycryptodome,markupsafe',
            *(name + '==' + version for name, version in names), timeout=1800)
        run(python, '-m', 'pip', 'check')


def recover(transaction):
    """Resume rollback after a killed worker or reboot, using the stopped-data backup."""
    backup = Path(transaction['backup'])
    data = Path(transaction['data'])
    def state(phase, message):
        write('status.json', {'phase': phase, 'message': message, 'backup': str(backup), 'target': transaction['target']})
    state('rolling_back', 'Recovering an interrupted update…')
    try:
        service('stop')
        if transaction['backup_complete']:
            run('git', 'reset', '--hard', transaction['old'])
            if (ROOT / '.venv').exists():
                shutil.rmtree(ROOT / '.venv')
            shutil.copytree(backup / 'venv', ROOT / '.venv', symlinks=True)
            if data.exists():
                shutil.rmtree(data)
            if (backup / 'data').exists():
                shutil.copytree(backup / 'data', data, symlinks=True)
            shutil.copy2(backup / 'meshcorestation.env', ROOT / 'meshcorestation.env')
        service('start')
        healthy(transaction['old'], transaction['port'])
        state('failed', 'Interrupted update rolled back. Previous installation restored.')
        (STATE / 'transaction.json').unlink(missing_ok=True)
    except Exception as exc:
        state('failed', f'Interrupted update needs recovery: {exc}. Backup: {backup}')
        raise


def worker():
    # Run by a separate systemd service, so stopping the dashboard cannot kill us.
    with lock():
        previous = read('transaction.json')
        if previous:
            recover(previous)
            return
        request = read('request.json')
        if not request:
            return
        (STATE / 'request.json').unlink()
        backup = None
        stopped = False
        backup_complete = False
        def status(phase, message):
            write('status.json', {'phase': phase, 'message': message,
                                 'target': request['target'], 'backup': str(backup) if backup else None})
        try:
            status('preparing', 'Checking source and available disk space…')
            validate_checkout()
            old, target = local_revision(), request['target']
            if old != request['current'] or not re.fullmatch('[0-9a-f]{40}', target):
                raise RuntimeError('Source changed since the update was checked.')
            run('git', 'merge-base', '--is-ancestor', old, target)
            from meshcorestation.config import DATA_DIR, PORT
            data = DATA_DIR
            if data == ROOT or ROOT.is_relative_to(data) or data.is_relative_to(STATE):
                raise RuntimeError('Unsupported data directory for automatic backup.')
            if (ROOT / '.venv').is_symlink() or data.is_symlink():
                raise RuntimeError('Symlinked runtime directories need a manual update.')
            size = sum(p.stat().st_size for base in (data, ROOT / '.venv') for p in base.rglob('*') if p.is_file())
            if shutil.disk_usage(ROOT).free < size * 2 + 512 * 1024**2:
                raise RuntimeError('Not enough free disk space for backup and dependency installation.')
            backup = STATE / ('backup-' + time.strftime('%Y%m%d-%H%M%S'))
            backup.mkdir(mode=0o700)
            status('backing_up', 'Stopping MeshcoreStation and backing up code, data and dependencies…')
            transaction = {'old': old, 'data': str(data), 'port': PORT,
                           'backup': str(backup), 'backup_complete': False, 'target': target}
            write('transaction.json', transaction)
            stopped = True
            service('stop')
            run('git', 'archive', '--format=tar', '-o', str(backup / 'source.tar'), old)
            shutil.copytree(ROOT / '.venv', backup / 'venv', symlinks=True)
            if data.exists():
                shutil.copytree(data, backup / 'data', symlinks=True)
            shutil.copy2(ROOT / 'meshcorestation.env', backup / 'meshcorestation.env')
            (backup / 'revision').write_text(old)
            backup_complete = True
            transaction['backup_complete'] = True
            write('transaction.json', transaction)
            status('installing', 'Installing the update and checking dependencies…')
            run('git', 'reset', '--hard', target)
            python = str(ROOT / '.venv/bin/python3')
            run(python, '-m', 'pip', 'install', '-r', 'requirements.txt', timeout=1800)
            check_dependencies(python)
            run(python, '-m', 'scripts.check_install')
            status('verifying', 'Restarting MeshcoreStation and checking the dashboard…')
            service('start')
            healthy(target, PORT)
            stopped = False
            status('complete', 'Update installed successfully. Reload the dashboard.')
            (STATE / 'transaction.json').unlink(missing_ok=True)
        except Exception as exc:
            error = str(exc)
            if stopped:
                try:
                    status('rolling_back', 'Update failed. Restoring the previous installation…')
                    service('stop')
                    if backup_complete:
                        run('git', 'reset', '--hard', old)
                        shutil.rmtree(ROOT / '.venv')
                        shutil.copytree(backup / 'venv', ROOT / '.venv', symlinks=True)
                        if data.exists():
                            shutil.rmtree(data)
                        if (backup / 'data').exists():
                            shutil.copytree(backup / 'data', data, symlinks=True)
                        shutil.copy2(backup / 'meshcorestation.env', ROOT / 'meshcorestation.env')
                    service('start')
                    healthy(old, PORT)
                    status('failed', f'Update failed; previous installation restored. {error}')
                    (STATE / 'transaction.json').unlink(missing_ok=True)
                except Exception as rollback:
                    status('failed', f'Update failed: {error}. Recovery needs attention: {rollback}. Backup: {backup}')
            else:
                status('failed', error)


if __name__ == '__main__':
    worker()
