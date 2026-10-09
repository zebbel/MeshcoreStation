import asyncio
import sqlite3
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
import pytest
from meshcorestation.radio.oled import DisplayTransport, DisplayError, OledDisplay, MAGIC, scene
from meshcorestation.storage.voltage_store import initialize


@pytest.fixture
def db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    initialize(db)
    db.execute('CREATE TABLE repeaters (public_key TEXT, name TEXT)')
    db.execute("INSERT INTO repeaters VALUES ('abc', 'DE_HE_HP_RPT1')")
    db.execute("UPDATE voltage_config SET public_key='abc'")
    yield db
    db.close()


def add(db, stamp, voltage, interval=1800):
    db.execute('INSERT INTO voltage_samples (public_key,name,sampled_at,voltage,voltage_channel,interval_seconds) VALUES (?,?,?,?,?,?)',
               ('abc', 'DE_HE_HP_RPT1', stamp, voltage, 1, interval))


def test_graph_has_real_24h_scale_and_gaps(db):
    now = 200000
    for stamp, v in [(now-86401, 9), (now-86400, 3.8), (now-84600, 3.9), (now-82800, None), (now-81000, 4), (now, 3.7)]:
        add(db, stamp, v)
    texts, runs = scene(db, now)
    assert len(runs) == 3
    assert runs[0][0][0] == 1 and runs[-1][-1][0] == 126
    assert any('3.70V ~20%' in t for _, _, t in texts)
    assert all(1 <= x <= 126 and 24 <= y <= 51 for run in runs for x,y in run)
    assert all(x+len(t)*6 <= 128 and y+8 <= 64 for x,y,t in texts)


def test_flat_history_missing_current_and_selection(db):
    add(db, 100000, 3.8)
    add(db, 101800, 3.8)
    texts, runs = scene(db, 102000)
    assert runs and all(y == runs[0][0][1] for run in runs for _,y in run)
    add(db, 102001, None)
    assert 'No current reading' in [t for _,_,t in scene(db,102002)[0]]
    db.execute("UPDATE voltage_config SET public_key='' ")
    assert scene(db,102002)[1] == []
    assert scene(db,102002)[0][0][2] == 'Select battery node'


def test_transport_matches_reply_and_preserves_normal_notifications():
    async def scenario():
        original = NS(handle_rx=AsyncMock())
        manager = NS(set_reader=Mock())
        companion = NS(mc=NS(_reader=original,connection_manager=manager), serial_command_lock=asyncio.Lock())
        transport = DisplayTransport(companion)
        async def send(payload):
            assert companion.serial_command_lock.locked()
            await transport.handle_rx(b'\x88normal notification')
            await transport.handle_rx(MAGIC + b'\x00\x00\x00') # wrong ID
            assert not transport.pending[2].done()
            await transport.handle_rx(payload[:8] + b'\x00\x80\x40\x10\x15\x00')
        manager.send = send
        assert await transport.command(0) == bytes([128,64,16,21,0])
        original.handle_rx.assert_awaited_once_with(b'\x88normal notification')
        assert transport.pending is None
        transport.detach()
        manager.set_reader.assert_called_with(original)
    asyncio.run(scenario())


def test_stock_firmware_error_does_not_reach_other_waiters():
    async def scenario():
        original = NS(handle_rx=AsyncMock())
        manager = NS(set_reader=Mock())
        transport = DisplayTransport(NS(mc=NS(_reader=original,connection_manager=manager),serial_command_lock=asyncio.Lock()))
        async def send(payload):
            await transport.handle_rx(b'\x01\x01')
        manager.send=send
        with pytest.raises(DisplayError):
            await transport.command(0)
        original.handle_rx.assert_not_called()
        assert transport.pending is None
    asyncio.run(scenario())


def test_graph_chunks_and_capacity(db, monkeypatch):
    import meshcorestation.radio.oled as oled
    now=200000
    monkeypatch.setattr(oled.time,'time',lambda:now)
    for i in range(127):
        add(db, now-86400+i*680, 3.7+i/1000, interval=680)
    display=OledDisplay(NS(database=NS(db=db)))
    display.transport=NS(command=AsyncMock())
    asyncio.run(display.draw((3,256,83)))
    calls=[c.args for c in display.transport.command.await_args_list]
    assert calls[0][0] == 1 and calls[-1][0] == 4
    polylines=[args for op,*rest in calls if op==9 for args in rest]
    assert len(polylines)==2
    assert all(2<=p[0]<=83 and len(p)==1+2*p[0] for p in polylines)
    assert polylines[0][-2:]==polylines[1][1:3]
    assert sum(p[0]-1 for p in polylines)+2<=256


def test_text_only_fallback(db):
    display=OledDisplay(NS(database=NS(db=db)))
    display.transport=NS(command=AsyncMock())
    asyncio.run(display.draw(None))
    calls=[c.args for c in display.transport.command.await_args_list]
    assert not any(c[0] in (8,9) for c in calls)
    assert calls[-1][0]==4


def test_unsupported_probe_stops_without_acquiring_display():
    display = OledDisplay(NS(logger=Mock()))
    display.transport = NS(command=AsyncMock(side_effect=DisplayError(3)))
    asyncio.run(display.run())
    display.transport.command.assert_awaited_once_with(0)
    assert not display.acquired


def test_draw_failure_releases_without_retrying_append(db):
    display = OledDisplay(NS(logger=Mock(), database=NS(db=db)))
    calls = []
    async def command(op, args=b''):
        calls.append(op)
        if op == 0:
            return bytes([128,64,16,21,0])
        if op == 7:
            return bytes([1,3,0,1,83])
        if op == 2:
            raise TimeoutError('uncertain append')
        return b''
    display.transport = NS(command=command)
    asyncio.run(display.run())
    assert calls == [0,7,1,2,5]
    assert not display.acquired
