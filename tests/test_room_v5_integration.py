"""Room coexistence and safety boundaries in the V5 runtime; never real RF."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import Mock, AsyncMock
import pytest
from meshcorestation.rooms.service import RoomService
from meshcorestation.rooms.server import RoomEndpoint, RoomWorker
from meshcorestation.rooms.wire import Packet
from meshcorestation.runtime import Runtime
from meshcorestation.storage import database
from meshcorestation.radio.companion import Companion
from meshcorestation.radio.companion_control import CompanionControl
from fake_companion import FakeMeshCore, KEY


def enabled(path):
    service = RoomService(path)
    rid = service.create('Persistent board')
    service.set_password(rid, 'room-pass')
    service.set_enabled(rid, True)
    return service, rid


def test_tx_waits_for_controls_and_rechecks_disable(tmp_path):
    async def run():
        service, rid = enabled(tmp_path / 'rooms.db')
        c = NS(mc=FakeMeshCore(),control_lock=asyncio.Lock(),reply_lock=asyncio.Lock(),logger=Mock())
        w, endpoint = RoomWorker(c,service), RoomEndpoint(service,rid)
        raw = endpoint.advert()
        await c.control_lock.acquire()
        sending = asyncio.create_task(w.transmit(raw,endpoint))
        await asyncio.sleep(0)
        assert not c.mc.commands.calls
        service.set_enabled(rid,False)
        c.control_lock.release()
        await sending
        assert not c.mc.commands.calls
        service.set_enabled(rid,True)
        await w.transmit(raw,endpoint)
        assert not c.mc.commands.calls
        endpoint = RoomEndpoint(service,rid)
        raw = endpoint.advert()
        await w.transmit(raw,endpoint)
        assert c.mc.commands.calls[-1] == ('send_raw_packet',raw,3)
        assert w.next_send > 0
    asyncio.run(run())


def test_bounded_rx_queue_and_close(tmp_path):
    async def run():
        service,rid = enabled(tmp_path/'rooms.db')
        c = NS(mc=FakeMeshCore(),control_lock=asyncio.Lock(),reply_lock=asyncio.Lock(),logger=Mock())
        w = RoomWorker(c,service)
        w.endpoints[rid] = RoomEndpoint(service,rid)
        event = NS(payload={'raw_hex':'00a00900'+'01'*20})
        for _ in range(140):w.on_rx(event)
        assert w.queue.qsize()==128 and w.dropped==12
        await w.close()
        assert w.queue.empty() and not w.endpoints
    asyncio.run(run())


def station(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_FILE',tmp_path/'meshcorestation.db')
    return database.Database(Mock())


def test_destination_switch_back_to_verified_channel(tmp_path,monkeypatch):
    db = station(tmp_path,monkeypatch)
    async def run():
        r = Runtime(Mock(),db)
        c = Companion(Mock(),db);c.mc=FakeMeshCore();c.channel_idx=0
        r.companion,r.control=c,CompanionControl(c)
        service,rid=enabled(r.room_path)
        assert (await r.dispatch({'operation':'room_bot','room':rid}))['ok']
        assert c.room_bot_id==rid and service.bot_room()==rid
        channels=await r.dispatch({'operation':'get_channels'})
        assert not channels['channels'][0]['protected']
        result=await r.dispatch(dict(operation='set_bot_channel',index=0,expected_revision=channels['revision'],expected_public_key=channels['public_key']))
        assert result['ok'],result
        assert c.room_bot_id is None and service.bot_room() is None
        await c.reply_retries.close()
    try:asyncio.run(run())
    finally:db.close()


def test_restart_preserves_identity_history_and_subscription_cleanup(tmp_path,monkeypatch):
    db=station(tmp_path,monkeypatch)
    async def run():
        r=Runtime(Mock(),db)
        service,rid=enabled(r.room_path);service.set_bot(rid)
        service.local_post(rid,'Saved before restart')
        key=service.config(rid)['public_key']
        c=Companion(Mock(),db);c.mc=FakeMeshCore();r.companion=c
        assert await r.start_rooms()
        first=r.rooms
        assert c.room_bot_id==rid
        assert await r.start_rooms()
        assert first.task is None and first.subscription is None
        assert r.rooms is not first
        assert service.config(rid)['public_key']==key
        assert service.details(rid)['posts'][0]['text']=='Saved before restart'
        await r.rooms.close();await c.reply_retries.close()
    try:asyncio.run(run())
    finally:db.close()


def test_permission_changes_expire_sessions_without_losing_posts(tmp_path):
    service,rid=enabled(tmp_path/'rooms.db');key='ab'*32
    service.grant(rid,key,'writer');service.post(rid,key,1,'Retained')
    endpoint=RoomEndpoint(service,rid);endpoint.sessions[key]=object()
    service.grant(rid,key,'reader')
    _,changed=endpoint.refresh_auth()
    assert changed and not endpoint.sessions
    assert service.details(rid)['posts'][0]['text']=='Retained'


def test_authenticated_history_deduplication_and_room_reply_status(tmp_path,monkeypatch):
    db=station(tmp_path,monkeypatch)
    async def run():
        r=Runtime(Mock(),db);c=Companion(Mock(),db);c.mc=FakeMeshCore();r.companion=c
        service,rid=enabled(r.room_path);service.set_bot(rid)
        assert await r.start_rooms()
        c.bot.match_command=lambda text:{'trigger':'ping'}
        c.bot.handle_message=AsyncMock(return_value='pong')
        post=dict(author='ab'*32,sender_timestamp=12,text='ping')
        rx=dict(path_len=None,path_hash_size=None,room_scope_name='direct',received_at=1234,snr=-2,rssi=-90)
        await r.handle_room_post(rid,post,rx);await r.handle_room_post(rid,post,rx)
        row=db.db.execute('SELECT * FROM logger').fetchone()
        assert row['recv_time']==1234 and row['sender_public_key']==post['author']
        assert row['room_public_key']==service.config(rid)['public_key']
        assert db.db.execute('SELECT count(*) FROM logger').fetchone()[0]==1
        reply=db.db.execute('SELECT * FROM command_replies').fetchone()
        assert reply['message']=='pong' and reply['send_status']=='queued'
        assert reply['retry_status']=='room synchronization'
        assert reply['channel_key_hash']=='room:'+str(rid)
        assert c.mc.commands.calls==['get_contacts']
        await r.rooms.close();await c.reply_retries.close()
    try:asyncio.run(run())
    finally:db.close()


def test_full_64_client_capacity_allows_dashboard_posts(tmp_path):
    service,rid=enabled(tmp_path/'rooms.db')
    for i in range(64):service.grant(rid,f'{i+1:064x}','writer')
    service.local_post(rid,'Dashboard post at full client capacity')
    with pytest.raises(ValueError,match='64'):service.grant(rid,f'{65:064x}','writer')
    assert service.details(rid)['posts'][0]['text']=='Dashboard post at full client capacity'


def test_position_command_authenticated_key_no_channel_send_or_unknown_scope_flood(tmp_path,monkeypatch):
    from meshcorestation.commands.actions import execute
    db=station(tmp_path,monkeypatch)
    async def run():
        c=Companion(Mock(),db);c.mc=FakeMeshCore()
        c.mc.commands.req_telemetry_sync=AsyncMock(return_value=[dict(type='gps',channel=1,value=dict(latitude=49.6,longitude=8.6))])
        message=dict(message='position',name='Renamed sender',room_id=1,sender_public_key=KEY)
        result=await execute(c.bot,'position',message,{'raw_hex':Packet(2,b'authenticated ciphertext').encode().hex()})
        assert result.ok
        assert c.mc.commands.req_telemetry_sync.await_args.args[0]['public_key']==KEY
        assert c.mc.commands.calls==['get_contacts']
        c.mc.commands.req_telemetry_sync.reset_mock()
        packet=Packet(2,b'authenticated ciphertext').encode(bytes(range(16)))
        result=await execute(c.bot,'position',message,{'raw_hex':packet.hex()})
        assert not result.ok
        c.mc.commands.req_telemetry_sync.assert_not_awaited()
        await c.reply_retries.close()
    try:asyncio.run(run())
    finally:db.close()
