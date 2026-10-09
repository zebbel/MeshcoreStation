"""Repair incompatible installed wheels without ignoring dependency failures."""
import argparse
from email.parser import Parser
from importlib.metadata import distribution
from pathlib import Path
import platform
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


# Narrow exception for the versions observed on Raspberry Pi OS Trixie.
# piwheels documents ARMv6 wheels renamed from ARMv7 builds:
# https://www.piwheels.org/faq.html#why-are-the-wheel-files-are-tagged-with-armv6-and-armv7
PIWHEELS_CHECKS = {
    'pyyaml': ('6.0.3', "import yaml; assert yaml.load('test: true', Loader=yaml.CSafeLoader) == {'test': True}"),
    'cffi': ('2.1.1', "from cffi import FFI; f=FFI(); p=f.new('int *', 42); assert p[0] == 42"),
    'tibs': ('0.5.7', "from tibs import Tibs; assert len(Tibs('0b101')) == 3"),
    'bitarray': ('3.11.0', "from bitarray import bitarray; assert bitarray('101').count() == 2"),
    'cryptography': ('50.0.2', "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; c=AESGCM(bytes(32)); n=bytes(12); assert c.decrypt(n,c.encrypt(n,b'test',None),None)==b'test'"),
}


def is_pi_zero():
    if sys.platform != 'linux' or platform.machine() != 'armv6l':
        return False
    try:
        return 'Raspberry Pi' in Path('/proc/device-tree/model').read_text()
    except OSError:
        return False


def supported_tags():
    from pip._vendor.packaging.tags import sys_tags
    return {str(tag) for tag in sys_tags()}


def verified_piwheels(name, version):
    rule = PIWHEELS_CHECKS.get(name.lower())
    if not rule or version != rule[0] or not is_pi_zero():
        return False
    installed = distribution(name)
    if installed.version != version:
        return False
    tags = Parser().parsestr(installed.read_text('WHEEL') or '').get_all('Tag', [])
    # Only a platform-label mismatch; interpreter/ABI must already match this Pi.
    if not tags or any(not tag.endswith('-linux_armv7l') for tag in tags):
        return False
    if not any(tag.removesuffix('linux_armv7l') + 'linux_armv6l' in supported_tags() for tag in tags):
        return False
    result = subprocess.run([sys.executable, '-c', rule[1]], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    if result.returncode:
        raise RuntimeError(f'{name} native runtime check failed; compatibility was NOT accepted: {result.stdout}')
    print(f'{name} {version}: ARMv7 metadata label accepted on this ARMv6 Pi after native runtime check. No rebuild needed.', flush=True)
    return True


def dependency_check():
    result = pip('check')
    if not result.returncode:
        return result
    accepted = set()
    for name, version in unsupported(result.stdout):
        if verified_piwheels(name, version):
            accepted.add(f'{name} {version} is not supported on this platform')
    lines = [line for line in result.stdout.splitlines() if line.strip() not in accepted]
    # Keep every other diagnostic, including dependency/version conflicts.
    output = '\n'.join(lines)
    return subprocess.CompletedProcess(result.args if hasattr(result, 'args') else [],
                                       result.returncode if output.strip() else 0, output)


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
    result = dependency_check()
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
    result = dependency_check()
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
    if dependency_check().returncode:
        raise RuntimeError('Dependency check still fails after wheel repair')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-build-tools', action='store_true')
    check(parser.parse_args().install_build_tools)
