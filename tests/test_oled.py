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


def test_button_events_interleaved_with_reply_and_sequence_wrap():
    import struct
    async def scenario():
        callback = Mock()
        original = NS(handle_rx=AsyncMock())
        manager = NS(set_reader=Mock())
        transport = DisplayTransport(NS(mc=NS(_reader=original, connection_manager=manager),
                                        serial_command_lock=asyncio.Lock()), callback)
        def event(sequence, gesture=1):
            return MAGIC + bytes([0, 0x80, 0, gesture]) + struct.pack('<HI', sequence, 123)
        async def send(payload):
            for data in (event(65535), event(65535), event(0), event(65534), event(1, 2),
                         event(2)[:-1]):
                await transport.handle_rx(data)
                assert not transport.pending[2].done()
            await transport.handle_rx(b'\x88radio')
            await transport.handle_rx(payload[:8] + b'\x00')
        manager.send = send
        assert await transport.command(4) == b''
        assert [c.args for c in callback.call_args_list] == [(1,), (1,), (2,)]
        original.handle_rx.assert_awaited_once_with(b'\x88radio')
    asyncio.run(scenario())


def test_command_page_latest_three_and_button_cycle(db):
    from meshcorestation.radio.oled import command_scene
    db.execute('CREATE TABLE logger (id INTEGER PRIMARY KEY, recv_time INTEGER, sender TEXT, message TEXT)')
    assert 'No commands yet' in [t for _, _, t in command_scene(db)[0]]
    for i in range(4):
        db.execute('INSERT INTO logger VALUES (?,?,?,?)', (i, 200000+i, 'Sender\n' + 'x'*30, f'command{i}'))
    texts, runs = command_scene(db)
    assert [t for _, _, t in texts if t.startswith('command')] == ['command3', 'command2', 'command1']
    assert not runs
    assert all(x+len(t)*6 <= 128 and y+8 <= 64 and all(32 <= ord(c) <= 126 for c in t)
               for x,y,t in texts)
    display = OledDisplay(NS(database=NS(db=db)))
    display.transport = NS(command=AsyncMock())
    display.on_button(1)
    assert display.page == 0  # No capability: battery remains available.
    display.buttons = True
    for gesture in (2,3,4):
        display.on_button(gesture)
    assert display.page == 0
    display.on_button(1)
    assert display.page == 1 and display.redraw.is_set()
    asyncio.run(display.draw((7,256,83)))
    calls = [c.args for c in display.transport.command.await_args_list]
    assert calls[0][0] == 1 and calls[1] == (10, b'\x01') and calls[-1][0] == 4
    assert not any(c[0] in (8,9) for c in calls)
    assert not any(b'Graph FW' in c[1] for c in calls if c[0] == 2)
    display.on_button(1)
    assert display.page == 0


def test_fixed_voltage_bounds(db):
    for i,v in enumerate((2.9,3.0,3.6,4.2,4.3)):
        add(db, 100000+i*1800, v)
    _,runs = scene(db,107200)
    assert [y for run in runs for _,y in run] == [51,51,37,24,24]


@pytest.mark.parametrize('model',['Heltec V3','Heltec V4 TFT','Heltec V4.3 TFT','Other',''])
def test_non_oled_v4_never_attaches_or_sends(model):
    display=OledDisplay(NS(device_info={'model':model}))
    display.start()
    assert display.transport is None and display.task is None and not display.compatible


def test_supported_model_probes_stock_once_and_releases_reader(monkeypatch):
    async def scenario():
        original=NS(handle_rx=AsyncMock())
        manager=NS(set_reader=Mock())
        companion=NS(device_info={'model':'Heltec V4 OLED'},logger=Mock(),
                     mc=NS(_reader=original,connection_manager=manager),serial_command_lock=asyncio.Lock())
        display=OledDisplay(companion)
        calls=[]
        async def send(payload):
            calls.append(payload)
            await display.transport.handle_rx(b'\x01\x01')
        manager.send=send
        display.start()
        await display.task
        assert len(calls)==1 and calls[0][7]==0
        assert not display.compatible and not display.acquired
        await display.close()
        manager.set_reader.assert_called_with(original)
    asyncio.run(scenario())
