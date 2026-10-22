"""Regression checks for shared V3 infrastructure and room command isolation."""
import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from flask import Flask
from meshcorestation.commands.delivery import ReplyDelivery
from meshcorestation.rooms.service import RoomService
from meshcorestation.rooms.server import RoomWorker
from meshcorestation.web.http import control_request_error, json_response
from meshcorestation import updater


@pytest.mark.parametrize('host,headers,allowed', [
    ('localhost', {'X-Meshcore-Control':'1'}, True),
    ('192.168.1.2', {'X-Meshcore-Control':'1','Origin':'http://192.168.1.2'}, True),
    ('localhost', {}, False),
    ('localhost', {'X-Meshcore-Control':'1','Origin':'https://attacker.test'}, False),
    ('localhost', {'X-Meshcore-Control':'1','Sec-Fetch-Site':'cross-site'}, False),
    ('attacker.test', {'X-Meshcore-Control':'1'}, False),
])
def test_shared_http_policy(host, headers, allowed):
    app = Flask(__name__)
    with app.test_request_context('/api/rooms', base_url='http://'+host, headers=headers):
        assert (control_request_error() is None) == allowed
        response = json_response({'ok':True})
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_delivery_preserves_only_accepted_parts():
    async def scenario():
        delivery = ReplyDelivery()
        async def send(part):
            if delivery.accepted:
                raise RuntimeError('offline')
            return part
        with pytest.raises(RuntimeError):
            await delivery.deliver('x'*121, send)
        assert delivery.text == 'x'*120 and delivery.status == 'partial'
        replacement = ReplyDelivery()
        async def replace(part): return 'scope not known'
        await replacement.deliver('x'*121, replace)
        assert replacement.text == 'scope not known' and replacement.status == 'partial'
        cancelled = ReplyDelivery()
        async def cancel(part): raise asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await cancelled.deliver('ping', cancel)
        assert cancelled.status == 'failed' and not cancelled.accepted
    asyncio.run(scenario())


def test_room_snapshot_one_connection_and_no_secrets(tmp_path):
    service = RoomService(tmp_path/'rooms.db')
    for name in ('One','Two','Three','Four'):
        room=service.create(name)
        service.set_password(room,'secret')
    count=0
    original=service.connect
    @contextmanager
    def counted():
        nonlocal count
        count+=1
        with original() as db:
            yield db
    service.connect=counted
    snapshot=service.snapshot()
    assert len(snapshot)==4 and count==1
    assert all('seed' not in row and 'password_hash' not in row and 'salt' not in row for row in snapshot)
    assert snapshot==[service.details(row['id']) for row in snapshot]


def worker(tmp_path, callback):
    service=RoomService(tmp_path/'rooms.db')
    room=service.create('Bot')
    service.set_password(room,'secret')
    service.set_enabled(room,True)
    service.grant(room,'ab'*32,'writer')
    companion=SimpleNamespace(
        room_bot_id=room, control_lock=asyncio.Lock(),
        bot=SimpleNamespace(match_command=lambda text: {'trigger':'ping'} if text=='ping' else None),
        logger=SimpleNamespace(warning=lambda *a:None))
    return RoomWorker(companion,service,callback),room


def test_room_commands_bounded_filtered_and_cancelled(tmp_path):
    async def scenario():
        entered, release=asyncio.Event(),asyncio.Event()
        async def slow(*args):
            entered.set()
            await release.wait()
        w,rid=worker(tmp_path,slow)
        post={'text':'ping','author':'ab'*32}
        w.enqueue_command(rid,dict(post,text='conversation'),{})
        w.enqueue_command(rid+1,post,{})
        assert w.command_queue.empty()
        w.command_task=asyncio.create_task(w.run_commands())
        w.enqueue_command(rid,post,{})
        await asyncio.wait_for(entered.wait(),1)
        # Slow callback occupies only command worker, enqueueing stays responsive.
        for _ in range(33):w.enqueue_command(rid,post,{})
        assert w.status()['queued_commands']==32 and w.dropped_commands==1
        task=w.command_task
        await asyncio.wait_for(w.close(),1)
        assert task.cancelled() and w.command_queue.empty()
        assert not w.companion.control_lock.locked()
    asyncio.run(scenario())


@pytest.mark.parametrize('change',['password','disable','reader','selected'])
def test_queued_commands_revalidate_access(tmp_path,change):
    async def scenario():
        calls=[]
        async def callback(*args):calls.append(args)
        w,rid=worker(tmp_path,callback)
        w.enqueue_command(rid,{'text':'ping','author':'ab'*32},{})
        if change=='password':w.service.set_password(rid,'changed')
        if change=='disable':w.service.set_enabled(rid,False)
        if change=='reader':w.service.grant(rid,'ab'*32,'reader')
        if change=='selected':w.companion.room_bot_id=None
        w.command_task=asyncio.create_task(w.run_commands())
        await asyncio.wait_for(w.command_queue.join(),1)
        await w.close()
        assert not calls
    asyncio.run(scenario())


def test_v3_update_branch_and_return_paths():
    assert updater.branch_name('feature/v3')=='feature/v3'
    assert updater.branch_name('feature/room-server')=='feature/room-server'
    assert updater.branch_name('main')=='main'
    with pytest.raises(RuntimeError):updater.branch_name('../unexpected')


def test_packet_loop_continues_during_slow_room_command(tmp_path,monkeypatch):
    from meshcore import EventType
    import meshcorestation.rooms.server as server
    from meshcorestation.rooms.wire import Packet

    async def scenario():
        entered, release, received_again = asyncio.Event(),asyncio.Event(),asyncio.Event()
        async def slow(*args):
            entered.set()
            await release.wait()
        w,rid=worker(tmp_path,slow)
        w.companion.database=SimpleNamespace(get_scopes=lambda:[])
        async def send(*args,**kwargs):return SimpleNamespace(type=EventType.OK)
        w.companion.mc=SimpleNamespace(
            subscribe=lambda *args:1,unsubscribe=lambda *args:None,
            commands=SimpleNamespace(send_raw_packet=send))
        class Endpoint:
            def __init__(self,service,room):
                self.room=room;self.sessions={};self.new_posts=[]
                self.last_advert=10**12;self.calls=0
            def receive(self,raw,scopes=()):
                self.calls+=1
                if self.calls==1:self.new_posts=[{'text':'ping','author':'ab'*32}]
                else:received_again.set()
                return []
            def next_push(self):return None
        monkeypatch.setattr(server,'RoomEndpoint',Endpoint)
        w.start()
        try:
            raw=Packet(2,b'test',1).encode()
            w.queue.put_nowait((raw,1,-90))
            await asyncio.wait_for(entered.wait(),1)
            w.queue.put_nowait((raw,1,-90))
            await asyncio.wait_for(received_again.wait(),1)
            assert not release.is_set()
        finally:
            await w.close()
    asyncio.run(scenario())
