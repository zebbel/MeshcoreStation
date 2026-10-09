"""Repair incompatible installed wheels without ignoring dependency failures."""
import argparse
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


def build_tools(packages, install=False):
    names = {name.lower().replace('_', '-') for name, _ in packages}
    required = ['python3-dev', 'build-essential', 'pkg-config']
    if names & {'cffi', 'cryptography'}:
        required.append('libffi-dev')
    if 'cryptography' in names:
        required.extend(['libssl-dev', 'rustc', 'cargo'])
    missing = []
    for package in required:
        result = subprocess.run(['dpkg-query', '-W', '-f=${Status}', package],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if result.returncode or result.stdout.strip() != 'install ok installed':
            missing.append(package)
    if not missing:
        return
    if not install:
        raise RuntimeError('Source rebuild needs system tools: ' + ' '.join(missing)
                           + '. Run meshcorestation update in the Pi terminal to install them.')
    print('No compatible wheel available; installing build tools: ' + ' '.join(missing), flush=True)
    options = ['-o', 'Acquire::ForceIPv4=true', '-o', 'Acquire::Retries=2',
               '-o', 'Acquire::http::Timeout=30', '-o', 'Acquire::https::Timeout=30']
    subprocess.run(['sudo', 'apt-get', *options, 'update'], check=True)
    subprocess.run(['sudo', 'apt-get', *options, 'install', '-y', *missing], check=True)


def check(install_build_tools=False):
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
        build_tools(remaining, install=install_build_tools)
        result = pip('install', '--force-reinstall', '--no-deps', '--no-cache-dir',
                     '--no-binary=' + ','.join(name for name, _ in remaining),
                     *(name + '==' + version for name, version in remaining))
        if result.returncode:
            raise RuntimeError('Native dependency rebuild failed. Check compiler, Rust, libffi and OpenSSL build dependencies in the log.')
    if pip('check').returncode:
        raise RuntimeError('Dependency check still fails after wheel repair')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-build-tools', action='store_true')
    check(parser.parse_args().install_build_tools)
