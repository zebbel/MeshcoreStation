"""Release-based, app-only Heltec V4 USB updates. Never erase the whole flash."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import time
import urllib.request
from meshcorestation import updater
from meshcorestation.config import DATA_DIR

REPO = 'zebbel/MeshCore'
TARGET = 'heltec_v4_companion_radio_usb'
MANIFEST = TARGET + '.json'
MAX_IMAGE = 8 * 1024 * 1024


def download(url, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'MeshcoreStation', 'Accept': 'application/vnd.github+json' if 'api.github.com' in url else 'application/octet-stream'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Release file exceeds size limit')
    return data


def releases():
    items = json.loads(download(f'https://api.github.com/repos/{REPO}/releases?per_page=50', 2_000_000))
    result = []
    for item in items:
        if item.get('draft'):
            continue
        assets = {a['name']: a for a in item.get('assets', [])}
        if MANIFEST in assets:
            result.append({'id': item['id'], 'tag': item['tag_name'], 'name': item['name'] or item['tag_name'],
                           'prerelease': item['prerelease'], 'assets': assets})
    return result


def asset(release, name, limit):
    entry = release['assets'].get(name, {})
    url = entry.get('browser_download_url', '')
    if not url.startswith(f'https://github.com/{REPO}/releases/download/'):
        raise ValueError('Missing release asset or unexpected download location')
    return download(url, limit)


def prepare(release):
    manifest = json.loads(asset(release, MANIFEST, 16384))
    if (manifest.get('schema') != 1 or manifest.get('target') != TARGET
            or manifest.get('chip') != 'esp32s3' or manifest.get('offset') != 0x10000):
        raise ValueError('Release is not a supported Heltec V4 OLED USB application')
    for key in ('sha256', 'partition_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', str(manifest.get(key, ''))):
            raise ValueError('Release checksum missing')
    image = asset(release, manifest.get('image'), MAX_IMAGE)
    if (len(image) < 64 or image[0] != 0xE9 or struct.unpack_from('<H', image, 12)[0] != 9
            or image[32:36] != b'\x32\x54\xcd\xab'):
        raise ValueError('Expected an ESP32-S3 application image, not a merged/factory image')
    if hashlib.sha256(image).hexdigest() != manifest['sha256']:
        raise ValueError('Firmware checksum does not match release manifest')
    return manifest, image


def validate_layout(backup, manifest, image_size):
    table = backup[0x8000:0x8C00]
    if hashlib.sha256(table).hexdigest() != manifest['partition_sha256']:
        raise ValueError('Installed partition layout differs from this build; use a manual firmware migration')
    apps, ota = [], None
    for offset in range(0, len(table), 32):
        record = table[offset:offset + 32]
        if record[:2] != b'\xaa\x50':
            break
        _, kind, subtype, start, size = struct.unpack_from('<HBBII', record)
        if kind == 0:
            apps.append((subtype, start, size))
        if kind == 1 and subtype == 0:
            ota = (start, size)
    app = next((a for a in apps if a[1] == 0x10000), None)
    if not app or app[0] not in (0, 0x10) or image_size > app[2]:
        raise ValueError('Application does not fit the supported first app partition')
    if ota:
        start, size = ota
        if size < 8192 or start + size > len(backup):
            raise ValueError('Invalid OTA partition')
        # Support stock initial boot_app0 (sequence 1) or erased OTA selection only.
        # Never guess the active slot of a device previously updated over OTA.
        sequences = [struct.unpack_from('<I', backup, start + sector)[0] for sector in (0, 4096)]
        if any(seq not in (1, 0xFFFFFFFF) for seq in sequences):
            raise ValueError('Device has an OTA slot selection; use a manual firmware update')
    elif app[0] != 0:
        raise ValueError('OTA application requires an OTA data partition')


class FirmwareUpdater:
    def __init__(self, runtime):
        self.runtime = runtime
        self.task = None
        self.catalog = []
        self.state = updater.read('firmware-status.json')
        if self.state.get('busy'):
            self.set_state('interrupted', 'Previous firmware update was interrupted. Check the companion before retrying.', busy=False)

    def set_state(self, phase, message, **values):
        self.state = {**self.state, 'phase': phase, 'message': message, **values}
        updater.write('firmware-status.json', self.state)

    async def request(self, payload):
        action = payload.get('action', 'status')
        if action == 'check':
            if self.task and not self.task.done():
                raise ValueError('Firmware update already running')
            self.catalog = await asyncio.to_thread(releases)
        elif action == 'install':
            if self.task and not self.task.done():
                raise ValueError('Firmware update already running')
            release = next((r for r in self.catalog if r['id'] == payload.get('release_id')), None)
            if not release or payload.get('confirm_heltec_v4') is not True:
                raise ValueError('Check releases and confirm the Heltec V4 OLED USB device first')
            if not importlib.util.find_spec('esptool'):
                raise ValueError('Install updated MeshcoreStation dependencies first (esptool missing)')
            if self.runtime.companion is None or self.runtime.control is None:
                raise ValueError('Connect the companion before starting a firmware update')
            self.set_state('queued', 'Preparing firmware update…', busy=True, release=release['tag'], log='')
            self.task = asyncio.create_task(self.install(release))
        elif action != 'status':
            raise ValueError('Unknown firmware operation')
        return {'ok': True, 'status': self.state, 'ready': importlib.util.find_spec('esptool') is not None,
                'device': self.runtime.device_info,
                'releases': [{k: r[k] for k in ('id', 'tag', 'name', 'prerelease')} for r in self.catalog]}

    async def tool(self, port, *args, timeout=600):
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-u', '-m', 'esptool', '--chip', 'esp32s3', '--port', port,
            '--baud', '460800', *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        async def consume():
            while True:
                chunk = await process.stdout.read(1024)
                if not chunk:
                    break
                self.set_state(self.state['phase'], self.state['message'],
                               log=(self.state.get('log', '') + chunk.decode(errors='replace'))[-6000:])
            if await process.wait():
                raise RuntimeError('Flashing tool failed. See the log. If connection failed, hold BOOT, tap RESET, release BOOT, then reconnect and retry.')
        try:
            await asyncio.wait_for(consume(), timeout)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def install(self, release):
        try:
            with updater.lock():
                await self._install(release)
        except Exception as exc:
            self.set_state('failed', str(exc), busy=False)

    async def _install(self, release):
        paused = False
        bootloader = False
        try:
            if updater.read('status.json').get('phase') in updater.ACTIVE or (updater.STATE / 'request.json').exists():
                raise ValueError('Wait for the MeshcoreStation update to finish')
            self.set_state('downloading', 'Downloading and verifying release…')
            manifest, image = await asyncio.to_thread(prepare, release)
            companion = self.runtime.companion
            if companion is None:
                raise ValueError('Companion disconnected before update')
            port = companion.serial_port
            directory = DATA_DIR / 'firmware-backups' / str(time.time_ns())
            directory.mkdir(parents=True, mode=0o700)
            firmware = directory / 'application.bin'
            firmware.write_bytes(image)
            self.set_state('pausing', 'Pausing radio commands and releasing USB…', backup=str(directory))
            paused = True
            await self.runtime.pause_for_firmware()
            self.set_state('backing_up', 'Entering bootloader and backing up all 16 MB of flash…')
            backup_path = directory / 'flash-backup.bin'
            bootloader = True
            await self.tool(port, '--after', 'no_reset', 'read_flash', '0', '0x1000000', str(backup_path))
            backup = backup_path.read_bytes()
            if len(backup) != 0x1000000:
                raise ValueError('Incomplete flash backup; nothing was written')
            validate_layout(backup, manifest, len(image))
            self.set_state('flashing', 'Writing application firmware; configuration partitions are preserved…')
            await self.tool(port, 'write_flash', '0x10000', str(firmware))
            bootloader = False
            self.set_state('reconnecting', 'Flash verified. Waiting for the companion to reconnect…')
            self.runtime.resume_after_firmware()
            paused = False
            for _ in range(90):
                await asyncio.sleep(1)
                if self.runtime.control is not None:
                    self.set_state('complete', 'Firmware installed and companion reconnected.', busy=False)
                    break
            else:
                raise RuntimeError('Flash succeeded, but companion reconnection was not confirmed. Check USB/serial settings and reset the device.')
        except Exception as exc:
            self.set_state('failed', str(exc), busy=False)
        finally:
            if paused:
                if bootloader:
                    try:
                        await self.tool(port, 'run', timeout=20)
                    except Exception:
                        pass
                self.runtime.resume_after_firmware()
