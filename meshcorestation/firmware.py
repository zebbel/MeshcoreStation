"""Device-selected firmware updates with explicit, validated flashing profiles."""
import asyncio
import concurrent.futures
import threading
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import urllib.request
from meshcorestation import updater
from meshcorestation.config import DATA_DIR

REPO = 'zebbel/MeshCore'
TARGET = 'heltec_v4_companion_radio_usb'
MANIFEST = TARGET + '.json'
MAX_IMAGE = 8 * 1024 * 1024

# Add a profile only after its image format and flashing procedure are tested.
# Model aliases come from DEVICE_QUERY, never from a release filename.
PROFILES = {
    TARGET: dict(label='Heltec V4 OLED USB',
                 models=('Heltec V4 OLED', 'Heltec V4.3 OLED'),
                 chip='esp32s3', image_chip_id=9, offset=0x10000,
                 installer='esptool_app'),
}


def profile_for_model(model):
    matches = [(target, profile) for target, profile in PROFILES.items() if model in profile['models']]
    return matches[0] if len(matches) == 1 else (None, None)


def manifest_name(name, target):
    return name == target + '.json' or bool(re.fullmatch(
        re.escape(target) + r'-[A-Za-z0-9_.-]+-meshcoreStation(?:-v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?)?\.json', name))



def download(url, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'MeshcoreStation', 'Accept': 'application/vnd.github+json' if 'api.github.com' in url else 'application/octet-stream'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Release file exceeds size limit')
    return data


def releases(target=TARGET):
    if target not in PROFILES:
        return []
    items = json.loads(download(f'https://api.github.com/repos/{REPO}/releases?per_page=50', 2_000_000))
    result = []
    for item in items:
        if item.get('draft'):
            continue
        assets = {a['name']: a for a in item.get('assets', [])}
        names = [n for n in assets if manifest_name(n, target)]
        if len(names) == 1:
            candidate = dict(assets=assets, manifest=names[0], target=target)
            try:
                read_manifest(candidate)
            except (ValueError, TypeError, KeyError):
                continue
            result.append({'id': item['id'], 'tag': item['tag_name'], 'name': item['name'] or item['tag_name'],
                           'prerelease': item['prerelease'], 'assets': assets, 'manifest': names[0], 'target': target})
    return result


def asset(release, name, limit):
    entry = release['assets'].get(name, {})
    url = entry.get('browser_download_url', '')
    if not url.startswith(f'https://github.com/{REPO}/releases/download/'):
        raise ValueError('Missing release asset or unexpected download location')
    return download(url, limit)


def read_manifest(release):
    target = release.get('target', TARGET)
    if target not in PROFILES:
        raise ValueError('Unsupported firmware target')
    profile = PROFILES[target]
    manifest = json.loads(asset(release, release.get('manifest', target + '.json'), 16384))
    if not isinstance(manifest, dict):
        raise ValueError('Invalid firmware manifest')
    if (manifest.get('schema') != 1 or manifest.get('target') != target
            or manifest.get('chip') != profile['chip'] or manifest.get('offset') != profile['offset']):
        raise ValueError('Release is not a supported application for the connected device')
    for key in ('sha256', 'partition_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', str(manifest.get(key, ''))):
            raise ValueError('Release checksum missing')
    name = manifest.get('image')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.bin', name) or 'merged' in name.lower() or 'factory' in name.lower():
        raise ValueError('Expected an application binary filename')
    if 'assets' in release and name not in release['assets']:
        raise ValueError('Application binary missing from release')
    return manifest


def prepare(release):
    manifest = read_manifest(release)
    image = asset(release, manifest['image'], MAX_IMAGE)
    if (len(image) < 64 or image[0] != 0xE9 or struct.unpack_from('<H', image, 12)[0] != PROFILES[manifest['target']]['image_chip_id']
            or image[32:36] != b'\x32\x54\xcd\xab'):
        raise ValueError('Expected an ESP32-S3 application image, not a merged/factory image')
    if hashlib.sha256(image).hexdigest() != manifest['sha256']:
        raise ValueError('Firmware checksum does not match release manifest')
    return manifest, image


def validate_layout(table, manifest, image_size):
    if len(table) != 0xC00:
        raise ValueError('Incomplete partition table; nothing was written')
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
        if size < 8192 or start < 0x9000 or start + size > 0x1000000 or start % 4096:
            raise ValueError('Invalid OTA partition')
    elif app[0] != 0:
        raise ValueError('OTA application requires an OTA data partition')
    return ota


def validate_boot_selection(data):
    if len(data) != 8192:
        raise ValueError('Incomplete boot selection read; nothing was written')
    # Never guess the active slot of a device previously updated over OTA.
    sequences = [struct.unpack_from('<I', data, sector)[0] for sector in (0, 4096)]
    if any(seq not in (1, 0xFFFFFFFF) for seq in sequences):
        raise ValueError('Device has an OTA slot selection; use a manual firmware update')



class FirmwareUpdater:
    def __init__(self, runtime):
        self.runtime = runtime
        self.task = None
        self.catalog = []
        self.catalog_device = None
        self.check_lock = threading.Lock()
        self.check_future = None
        self.check_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="firmware-releases")
        self.state = updater.read('firmware-status.json')
        if self.state.get('busy'):
            self.set_state('interrupted', 'Previous firmware update was interrupted. Check the companion before retrying.', busy=False)

    def set_state(self, phase, message, **values):
        self.state = {**self.state, 'phase': phase, 'message': message, **values}
        updater.write('firmware-status.json', self.state)

    def device_identity(self):
        companion = self.runtime.companion
        mc = getattr(companion, 'mc', None)
        connected = bool(mc and getattr(getattr(mc, 'connection_manager', None), 'is_connected', False))
        model = self.runtime.device_info.get('model')
        if not connected or self.runtime.control is None or profile_for_model(model)[0] is None:
            return None
        return (id(companion), companion.serial_port, model, (getattr(mc, 'self_info', None) or {}).get('public_key'))

    def snapshot(self):
        # Immutable-by-replacement snapshots; no radio-loop handoff for HTTP reads.
        identity = self.device_identity()
        supported = identity is not None
        target, profile = profile_for_model(self.runtime.device_info.get('model'))
        mc = getattr(self.runtime.companion, 'mc', None)
        connected = bool(mc and getattr(getattr(mc, 'connection_manager', None), 'is_connected', False))
        reason = 'Connect a companion to check firmware updates.' if not connected else 'No automatic firmware update profile is available for ' + str(self.runtime.device_info.get('model') or 'this unrecognized device') + '.'
        return {'ok': True, 'status': dict(self.state),
                'supported': supported, 'connected': connected,
                'target': target if supported else None,
                'target_label': profile['label'] if supported else None,
                'compatibility_message': '' if supported else reason,
                'ready': supported and importlib.util.find_spec('esptool') is not None,
                'device': dict(self.runtime.device_info),
                'releases': [{k: r[k] for k in ('id', 'tag', 'name', 'prerelease')} for r in self.catalog if identity is not None and identity == self.catalog_device and r.get('target', TARGET) == target]}

    def check_releases(self):
        """Runs on an HTTP worker, independent of radio connectivity/activity."""
        if not self.check_lock.acquire(blocking=False):
            raise ValueError('A firmware release check is already running.')
        try:
            if self.state.get('busy'):
                raise ValueError('Firmware update already running')
            if self.check_future is not None and not self.check_future.done():
                raise ValueError('The previous GitHub request is still finishing; try again shortly.')
            identity = self.device_identity()
            self.catalog = []
            self.catalog_device = None
            if identity is None:
                return self.snapshot()
            self.check_future = self.check_pool.submit(releases, profile_for_model(identity[2])[0])
            try:
                catalog = self.check_future.result(timeout=25)
            except concurrent.futures.TimeoutError:
                raise TimeoutError('GitHub release check timed out after 25 seconds. Check the Pi network and retry.') from None
            if self.device_identity() != identity:
                raise ValueError('Connected device changed. Check releases again.')
            self.catalog = catalog
            self.catalog_device = identity
            return self.snapshot()
        finally:
            self.check_lock.release()

    async def request(self, payload):
        action = payload.get('action', 'status')
        if action == 'install':
            if self.task and not self.task.done():
                raise ValueError('Firmware update already running')
            release = next((r for r in self.catalog if r['id'] == payload.get('release_id')), None)
            if not release or self.device_identity() is None or self.device_identity() != self.catalog_device or not (payload.get('confirm_device') is True and payload.get('target') == profile_for_model(self.runtime.device_info.get('model'))[0] or payload.get('confirm_heltec_v4') is True and profile_for_model(self.runtime.device_info.get('model'))[0] == TARGET):
                raise ValueError('Check releases and confirm the currently connected device first')
            if not importlib.util.find_spec('esptool'):
                raise ValueError('Install updated MeshcoreStation dependencies first (esptool missing)')
            if self.runtime.companion is None or self.runtime.control is None:
                raise ValueError('Connect the companion before starting a firmware update')
            target = profile_for_model(self.runtime.device_info.get('model'))[0]
            if release.get('target', TARGET) != target:
                raise ValueError('Release target does not match the connected device')
            self.set_state('queued', 'Preparing firmware update…', busy=True, release=release['tag'], log='', backup=None)
            self.task = asyncio.create_task(self.install({**release, '_device': self.device_identity()}))
        elif action != 'status':
            raise ValueError('Unknown firmware operation')
        return self.snapshot()

    async def tool(self, port, *args, timeout=600, chip='esp32s3'):
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-u', '-m', 'esptool', '--chip', chip, '--port', port,
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
        staging = None
        try:
            if updater.read('status.json').get('phase') in updater.ACTIVE or (updater.STATE / 'request.json').exists():
                raise ValueError('Wait for the MeshcoreStation update to finish')
            identity = self.device_identity()
            if identity is None or release.get('_device', identity) != identity:
                raise ValueError('Connected device is unsupported or changed; check releases again')
            target, profile = profile_for_model(identity[2])
            if release.get('target', TARGET) != target or profile['installer'] != 'esptool_app':
                raise ValueError('Release or installer does not match the connected device')
            self.set_state('downloading', 'Downloading and verifying release…')
            manifest, image = await asyncio.to_thread(prepare, release)
            companion = self.runtime.companion
            if companion is None or self.device_identity() != identity:
                raise ValueError('Companion disconnected or changed before update')
            port = companion.serial_port
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            staging = tempfile.TemporaryDirectory(prefix='firmware-update-', dir=DATA_DIR)
            directory = Path(staging.name)
            firmware = directory / 'application.bin'
            firmware.write_bytes(image)
            self.set_state('pausing', 'Pausing radio commands and releasing USB…', backup=None)
            paused = True
            await self.runtime.pause_for_firmware()
            self.set_state('validating', 'Checking partition layout and boot selection…')
            table_path = directory / 'partitions.bin'
            bootloader = True
            await self.tool(port, '--after', 'no_reset', 'read_flash', '0x8000', '0xc00', str(table_path), chip=profile['chip'])
            ota = validate_layout(table_path.read_bytes(), manifest, len(image))
            if ota:
                ota_path = directory / 'boot-selection.bin'
                await self.tool(port, '--after', 'no_reset', 'read_flash', hex(ota[0]), '0x2000', str(ota_path), chip=profile['chip'])
                validate_boot_selection(ota_path.read_bytes())
            self.set_state('flashing', 'Writing application firmware; configuration partitions are preserved…')
            await self.tool(port, 'write_flash', hex(profile['offset']), str(firmware), chip=profile['chip'])
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
                        await self.tool(port, 'run', timeout=20, chip=profile['chip'])
                    except Exception:
                        pass
                self.runtime.resume_after_firmware()
            if staging is not None:
                staging.cleanup()
