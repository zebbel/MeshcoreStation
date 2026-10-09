import asyncio
import hashlib
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from flask import Flask
from meshcorestation import firmware as fw
from meshcorestation.web.firmware_api import register_firmware_routes


def fixture_image():
    data = bytearray(256)
    data[0] = 0xE9
    struct.pack_into('<H', data, 12, 9)
    data[32:36] = b'\x32\x54\xcd\xab'
    return bytes(data)


def fixture_flash():
    data = bytearray(b'\xff' * 0x1000000)
    struct.pack_into('<HBBII', data, 0x8000, 0x50AA, 1, 0, 0xE000, 8192)
    struct.pack_into('<HBBII', data, 0x8020, 0x50AA, 0, 0x10, 0x10000, 0x300000)
    return data


def manifest(data):
    return {'schema': 1, 'target': fw.TARGET, 'chip': 'esp32s3', 'offset': 0x10000,
            'image': 'app.bin', 'sha256': hashlib.sha256(fixture_image()).hexdigest(),
            'partition_sha256': hashlib.sha256(data[0x8000:0x8C00]).hexdigest()}


def validate_flash(flash, expected, size):
    ota = fw.validate_layout(flash[0x8000:0x8C00], expected, size)
    if ota:
        fw.validate_boot_selection(flash[ota[0]:ota[0] + 8192])


def test_partition_guards():
    backup = fixture_flash()
    expected = manifest(backup)
    validate_flash(backup, expected, 256)
    struct.pack_into('<I', backup, 0xE000, 1)
    validate_flash(backup, expected, 256)
    struct.pack_into('<I', backup, 0xE000, 2)
    with pytest.raises(ValueError, match='OTA slot'):
        validate_flash(backup, expected, 256)
    with pytest.raises(ValueError, match='fit'):
        validate_flash(backup, expected, 0x300001)
    backup[0x8005] ^= 1
    with pytest.raises(ValueError, match='layout differs'):
        validate_flash(backup, expected, 256)


def test_download_guards(monkeypatch):
    import json
    data = fixture_flash()
    expected = manifest(data)
    image = fixture_image()
    monkeypatch.setattr(fw, 'asset', lambda release, name, limit: json.dumps(expected).encode() if name == fw.MANIFEST else image)
    assert fw.prepare({})[1] == image
    expected['target'] = 'another-board'
    with pytest.raises(ValueError, match='not a supported'):
        fw.prepare({})
    expected['target'] = fw.TARGET
    image = image[:-1] + b'\x01'
    with pytest.raises(ValueError, match='checksum'):
        fw.prepare({})
    image = b'\xff' * 256
    with pytest.raises(ValueError, match='application image'):
        fw.prepare({})


def test_no_external_asset():
    with pytest.raises(ValueError, match='download location'):
        fw.asset({'assets': {'app.bin': {'browser_download_url': 'https://example.com/app.bin'}}}, 'app.bin', 10)


@pytest.fixture
def manager(monkeypatch, tmp_path):
    monkeypatch.setattr(fw.updater, 'STATE', tmp_path / 'state')
    monkeypatch.setattr(fw, 'DATA_DIR', tmp_path / 'data')
    runtime = SimpleNamespace(companion=SimpleNamespace(serial_port='/dev/test'), control=object(),
                              device_info={}, pause_for_firmware=AsyncMock(), resume_after_firmware=lambda: None)
    return fw.FirmwareUpdater(runtime)


def test_layout_failure_never_writes_and_resumes(manager, monkeypatch):
    backup = fixture_flash()
    expected = manifest(backup)
    expected['partition_sha256'] = '0' * 64
    monkeypatch.setattr(fw, 'prepare', lambda _: (expected, fixture_image()))
    calls = []
    async def tool(port, *args, **kwargs):
        calls.append(args)
        if 'read_flash' in args:
            from pathlib import Path
            start, length = int(args[-3], 0), int(args[-2], 0)
            Path(args[-1]).write_bytes(backup[start:start + length])
    manager.tool = tool
    resumed = []
    manager.runtime.resume_after_firmware = lambda: resumed.append(True)
    asyncio.run(manager.install({'tag': 'test'}))
    assert manager.state['phase'] == 'failed'
    assert 'layout differs' in manager.state['message']
    assert not any('write_flash' in args for args in calls)
    assert resumed == [True]


def test_pause_failure_never_opens_flash_tool(manager, monkeypatch):
    monkeypatch.setattr(fw, 'prepare', lambda _: (manifest(fixture_flash()), fixture_image()))
    manager.runtime.pause_for_firmware.side_effect = RuntimeError('USB close failed')
    manager.tool = AsyncMock()
    asyncio.run(manager.install({'tag': 'test'}))
    manager.tool.assert_not_called()
    assert manager.state['phase'] == 'failed'


def test_update_lock_blocks_firmware(manager):
    with fw.updater.lock():
        asyncio.run(manager.install({'tag': 'test'}))
    assert manager.state['phase'] == 'failed'
    assert 'already running' in manager.state['message']


def test_request_requires_checked_release(manager):
    with pytest.raises(ValueError, match='Check releases'):
        asyncio.run(manager.request({'action': 'install', 'release_id': 42, 'confirm_heltec_v4': True}))


def test_http_guard(monkeypatch):
    from meshcorestation.web import firmware_api
    app = Flask(__name__)
    register_firmware_routes(app)
    monkeypatch.setattr(firmware_api.bridge, 'runtime', SimpleNamespace(firmware=SimpleNamespace(snapshot=lambda: {'ok': True, 'status': {}})))
    client = app.test_client()
    assert client.get('/api/companion/firmware').status_code == 403
    headers = {'X-Meshcore-Control': '1'}
    assert client.get('/api/companion/firmware', headers=headers).status_code == 200
    assert client.post('/api/companion/firmware', headers={**headers, 'Origin': 'https://evil.example'}, json={}).status_code == 403
    assert client.post('/api/companion/firmware', headers=headers, json=[]).status_code == 409


def test_runtime_pause_handshake(manager):
    from meshcorestation.runtime import Runtime
    async def scenario():
        runtime = Runtime.__new__(Runtime)
        runtime.usb_closed = asyncio.Event()
        runtime.resume_radio = asyncio.Event()
        runtime.reconnect_requested = asyncio.Event()
        runtime.maintenance = False
        task = asyncio.create_task(runtime.pause_for_firmware())
        await asyncio.sleep(0)
        assert runtime.maintenance and runtime.reconnect_requested.is_set()
        assert not task.done()
        runtime.usb_closed.set()
        await task
        runtime.resume_after_firmware()
        assert not runtime.maintenance and runtime.resume_radio.is_set()
    asyncio.run(scenario())


def test_success_reads_only_metadata_then_writes_app(manager, monkeypatch):
    backup = fixture_flash()
    monkeypatch.setattr(fw, 'prepare', lambda _: (manifest(backup), fixture_image()))
    calls = []
    async def tool(port, *args, **kwargs):
        manager.runtime.pause_for_firmware.assert_awaited_once()
        calls.append(args)
        if 'read_flash' in args:
            from pathlib import Path
            start, length = int(args[-3], 0), int(args[-2], 0)
            Path(args[-1]).write_bytes(backup[start:start + length])
    manager.tool = tool
    monkeypatch.setattr(fw.asyncio, 'sleep', AsyncMock())
    resumed = []
    manager.runtime.resume_after_firmware = lambda: resumed.append(True)
    asyncio.run(manager.install({'tag': 'test'}))
    assert calls[0][:-1] == ('--after', 'no_reset', 'read_flash', '0x8000', '0xc00')
    assert calls[1][:-1] == ('--after', 'no_reset', 'read_flash', '0xe000', '0x2000')
    assert calls[2][:2] == ('write_flash', '0x10000')
    assert len(calls) == 3
    from pathlib import Path
    assert not Path(calls[0][-1]).parent.exists()
    assert manager.state.get('backup') is None
    assert resumed == [True]
    assert manager.state['phase'] == 'complete' and manager.state['busy'] is False


def test_packaging_roundtrip(tmp_path):
    import json
    from scripts.package_companion_firmware import package
    build = tmp_path / 'build'
    build.mkdir()
    (build / 'firmware.bin').write_bytes(fixture_image())
    flash = fixture_flash()
    (build / 'partitions.bin').write_bytes(flash[0x8000:0x8C00])
    output = tmp_path / 'release'
    package(build, output)
    result = json.loads((output / fw.MANIFEST).read_text())
    validate_flash(flash, result, len(fixture_image()))
    assert hashlib.sha256((output / result['image']).read_bytes()).hexdigest() == result['sha256']


def test_release_check_and_status_never_use_radio_bridge(manager, monkeypatch):
    from meshcorestation.web import firmware_api
    monkeypatch.setattr(fw, 'releases', lambda: [{'id': 7, 'tag': 'test', 'name': 'test', 'prerelease': False, 'assets': {}}])
    monkeypatch.setattr(firmware_api.bridge, 'runtime', SimpleNamespace(firmware=manager))
    def forbidden(*a, **kw):
        raise AssertionError('Radio runtime must not be called')
    monkeypatch.setattr(firmware_api.bridge, 'request', forbidden)
    app = Flask(__name__)
    register_firmware_routes(app)
    client = app.test_client()
    headers = {'X-Meshcore-Control': '1'}
    response = client.post('/api/companion/firmware', json={'action': 'check'}, headers=headers)
    assert response.status_code == 200
    assert response.json['releases'][0]['id'] == 7
    assert client.get('/api/companion/firmware', headers=headers).json['releases'][0]['id'] == 7
    manager.check_pool.shutdown()


def test_release_timeout_keeps_status_readable_and_prevents_duplicate(manager):
    import concurrent.futures
    class Pending:
        def result(self, timeout):
            assert timeout == 25
            raise concurrent.futures.TimeoutError()
        def done(self):
            return False
    manager.check_pool.shutdown()
    calls = []
    manager.check_pool = SimpleNamespace(submit=lambda *a: calls.append(a) or Pending())
    with pytest.raises(TimeoutError, match='25 seconds'):
        manager.check_releases()
    assert manager.snapshot()['ok']
    with pytest.raises(ValueError, match='previous GitHub'):
        manager.check_releases()
    assert len(calls) == 1


def test_short_metadata_reads_are_rejected():
    with pytest.raises(ValueError, match='Incomplete partition'):
        fw.validate_layout(b'', {}, 256)
    with pytest.raises(ValueError, match='Incomplete boot'):
        fw.validate_boot_selection(b'\xff' * 4096)
