"""Repair incompatible installed wheels without ignoring dependency failures."""
import re
import subprocess
import sys


def unsupported(output):
    # Restrict both fields before converting diagnostic text into pip arguments.
    return list(dict.fromkeys(re.findall(
        r'^([A-Za-z0-9][A-Za-z0-9._-]*) ([A-Za-z0-9][A-Za-z0-9.!+_-]*) is not supported on this platform\s*$',
        output, re.M)))


def pip(*args):
    result = subprocess.run([sys.executable, '-m', 'pip', *args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
    print(result.stdout, end='', flush=True)
    return result


def check():
    result = pip('check')
    if result.returncode == 0:
        return
    packages = unsupported(result.stdout)
    if not packages:
        raise RuntimeError('Dependency check failed; no unsupported wheels to repair')
    for name, version in packages:
        # The Pi's configured wheel mirror may have supplied invalid wheel metadata.
        # Prefer an official compatible wheel to compiling crypto/Rust on the Pi.
        pip('install', '--force-reinstall', '--no-deps', '--no-cache-dir',
            '--index-url', 'https://pypi.org/simple', '--only-binary=:all:', name + '==' + version)
    result = pip('check')
    if result.returncode == 0:
        return
    remaining = unsupported(result.stdout)
    if remaining:
        result = pip('install', '--force-reinstall', '--no-deps', '--no-cache-dir',
                     '--no-binary=' + ','.join(name for name, _ in remaining),
                     *(name + '==' + version for name, version in remaining))
        if result.returncode:
            raise RuntimeError('Native dependency rebuild failed. Check compiler, Rust, libffi and OpenSSL build dependencies in the log.')
    if pip('check').returncode:
        raise RuntimeError('Dependency check still fails after wheel repair')


if __name__ == '__main__':
    check()
