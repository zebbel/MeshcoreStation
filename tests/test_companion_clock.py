import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
import pytest
from meshcore import EventType
from meshcorestation.radio import clock

NOW = 1791550948


def event(kind, payload=None):
    return NS(type=kind, payload=payload or {})


def commands(*times):
    return NS(get_time=AsyncMock(side_effect=[event(EventType.CURRENT_TIME, {'time': t}) for t in times]),
              set_time=AsyncMock(return_value=event(EventType.OK)))


@pytest.fixture(autouse=True)
def host(monkeypatch):
    monkeypatch.setattr(clock.time, 'time', lambda: NOW)


def test_reported_stale_clock_is_synchronized_and_verified():
    c = commands(1791220776, NOW)
    asyncio.run(clock.synchronize_clock(c, Mock()))
    c.set_time.assert_awaited_once_with(NOW)
    assert c.get_time.await_count == 2


@pytest.mark.parametrize('ahead', [0, 1, 5])
def test_current_clock_is_not_moved_backwards(ahead):
    c = commands(NOW + ahead)
    asyncio.run(clock.synchronize_clock(c, Mock()))
    c.set_time.assert_not_called()


def test_future_clock_is_reported():
    c = commands(NOW + 300)
    with pytest.raises(RuntimeError, match='ahead'):
        asyncio.run(clock.synchronize_clock(c, Mock()))
    c.set_time.assert_not_called()


def test_invalid_pi_clock_cannot_poison_device(monkeypatch):
    monkeypatch.setattr(clock.time, 'time', lambda: 10)
    c = commands(0)
    with pytest.raises(RuntimeError, match='Pi clock'):
        asyncio.run(clock.synchronize_clock(c, Mock()))
    c.get_time.assert_not_called()
    c.set_time.assert_not_called()


@pytest.mark.parametrize('value', [None, '123', True, -1])
def test_invalid_device_time(value):
    c = commands(value)
    with pytest.raises(RuntimeError, match='invalid clock'):
        asyncio.run(clock.synchronize_clock(c, Mock()))
    c.set_time.assert_not_called()


def test_rejected_set_does_not_claim_success():
    c = commands(0)
    c.set_time.return_value = event(EventType.ERROR)
    with pytest.raises(RuntimeError, match='rejected'):
        asyncio.run(clock.synchronize_clock(c, Mock()))


def test_wrong_readback_does_not_claim_success():
    c = commands(0, 1)
    with pytest.raises(RuntimeError, match='verified'):
        asyncio.run(clock.synchronize_clock(c, Mock()))


def test_every_connection_syncs_before_other_initialization(monkeypatch):
    from meshcorestation.radio import companion as module
    async def scenario():
        c = module.Companion.__new__(module.Companion)
        c.logger = Mock()
        c.serial_port = '/dev/test'
        c.channel_name = 'test'
        c.database = Mock()
        c.get_self_info = AsyncMock(return_value={'adv_lat': 1, 'adv_lon': 2})
        order = []
        async def sync(*args):
            order.append('clock')
        async def channel(*args):
            order.append('channel')
            return 0, {}
        c._find_channel_by_name = channel
        mc = NS(commands=NS(send=AsyncMock()), set_decrypt_channel_logs=Mock())
        monkeypatch.setattr(module.MeshCore, 'create_serial', AsyncMock(return_value=mc))
        monkeypatch.setattr(module, 'synchronize_clock', sync)
        assert await c.connect()
        assert await c.connect()
        assert order == ['clock', 'channel', 'clock', 'channel']
    asyncio.run(scenario())
