"""Installer service-recovery tests, with mock systemd and no host changes."""
import os
from pathlib import Path
import re
import subprocess
import pytest

INSTALLER = Path(__file__).resolve().parents[1] / 'install.sh'


def function(name):
    match = re.search(r'^' + re.escape(name) + r'\(\) \{\n.*?^\}\n',
                      INSTALLER.read_text(), re.M | re.S)
    assert match, f'{name} missing'
    return match.group(0)


def run(tmp_path, name, *, state='enabled', ready=True, active=True, arg=''):
    commands = {
        'systemctl': '''#!/bin/sh
if [ "$1" = "is-enabled" ]; then
    echo "$MOCK_STATE"
    [ "$MOCK_STATE" = enabled ] && exit 0 || exit 1
fi
if [ "$1" = "is-active" ]; then
    [ "$MOCK_ACTIVE" = yes ] && exit 0 || exit 1
fi
exit 1
''',
        'sudo': '''#!/bin/sh
printf '%s\\n' "$*" >> "$MOCK_ACTIONS"
''',
        'python3': '''#!/bin/sh
[ "$MOCK_READY" = yes ]
'''
    }
    for name_, body in commands.items():
        file = tmp_path / name_
        file.write_text(body)
        file.chmod(0o755)
    actions = tmp_path / 'actions.log'
    env = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'],
           'MOCK_STATE': state, 'MOCK_READY': 'yes' if ready else 'no',
           'MOCK_ACTIVE': 'yes' if active else 'no', 'MOCK_ACTIONS': str(actions)}
    script = ('set -Eeuo pipefail\nservice=meshcorestation.service\n'
              'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
              + function(name) + '\n' + name + (' ' + arg if arg else '') + '\n')
    result = subprocess.run(['bash', '-c', script], env=env,
                            text=True, capture_output=True)
    return result, actions.read_text() if actions.exists() else ''


def test_bash_syntax():
    subprocess.run(['bash', '-n', str(INSTALLER)], check=True)


@pytest.mark.parametrize('state,expected', [
    ('masked', True), ('masked-runtime', True), ('enabled', False),
    ('disabled', False), ('not-found', False)])
def test_unmask_only_masked_units(tmp_path, state, expected):
    result, actions = run(tmp_path, 'unmask_service_if_needed', state=state)
    assert result.returncode == 0, result.stderr
    assert ('systemctl unmask meshcorestation.service' in actions) == expected


def test_healthy_startup(tmp_path):
    result, actions = run(tmp_path, 'verify_station_startup', arg='80')
    assert result.returncode == 0, result.stderr
    assert 'passed startup validation' in result.stdout
    assert not actions


@pytest.mark.parametrize('state,ready,active,message', [
    ('disabled', True, True, 'not enabled'),
    ('enabled', False, True, 'startup validation failed'),
    ('enabled', True, False, 'stopped during startup validation')])
def test_startup_failures_show_diagnostics(tmp_path, state, ready, active, message):
    result, actions = run(tmp_path, 'verify_station_startup', state=state,
                          ready=ready, active=active, arg='80')
    assert result.returncode != 0
    assert message in result.stderr
    assert 'systemctl status meshcorestation.service' in actions
    if state != 'disabled':
        assert 'journalctl -u meshcorestation.service' in actions


def test_install_flow_contains_recovery_and_health_gate():
    text = INSTALLER.read_text()
    service = text.split('install_service_files() {', 1)[1].split('\n}\n', 1)[0]
    assert service.index('unmask_service_if_needed') < service.index(
        'sudo install -o root -g root -m 0644')
    install = text.split('\ninstall_project() (', 1)[1].split('\n)\n', 1)[0]
    assert install.index('show_platform') < install.index('install_python_dependencies')
    assert install.index('sudo systemctl enable --now "$service"') < install.index(
        'verify_station_startup "$web_port"')
