"""Clock scheduler integration uses fake Companion transport only, never serial/RF."""
import asyncio
from contextlib import closing
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
import pytest
from meshcore import EventType
from meshcorestation.storage.connection import connect
from meshcorestation import config
from meshcorestation.storage import database, voltage_store, clock_sync as store
from meshcorestation.radio import clock_sync as radio
from fake_companion import FakeMeshCore, KEY, OTHER, event


@pytest.fixture
def station(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_FILE', tmp_path/'meshcorestation.db')
    monkeypatch.setattr(config, 'DB_PATH', database.DB_FILE)
    owner = database.Database(Mock())
    for key in (KEY, OTHER):
        owner.add_new_repeater(NS(payload=dict(type=2,public_key=key,adv_name='Test')),observed=False)
        with owner.db: voltage_store.ensure_repeater(owner.db,key)
    yield owner
    owner.close()


def ready(key=KEY):
    store.save(database.DB_FILE,key,True,24,store.settings(database.DB_FILE,key)['revision'])
    # Simulate the first persisted due time having elapsed, without changing wall time.
    with closing(connect(database.DB_FILE)) as db, db:
        db.execute('UPDATE repeater_clock_sync SET next_due=? WHERE public_key=?',(time.time()-1,key))
    return store.settings(database.DB_FILE,key)


def fixture_worker(monkeypatch, *, lag=30, admin=True, failure=None, bad_identity=False):
    companion=NS(mc=FakeMeshCore(), control_lock=asyncio.Lock())
    companion.mc.contacts[OTHER]=dict(public_key=OTHER,type=2,adv_name='Other managed repeater')
    commands=companion.mc.commands
    state={'lag':lag,'writes':[],'logins':[]}
    async def login(contact,password,**kw):
        assert companion.control_lock.locked() and password==''
        state['logins'].append(contact['public_key'])
        return event(EventType.LOGIN_SUCCESS,pubkey_prefix=OTHER[:12] if bad_identity else contact['public_key'][:12],
                     is_admin=admin or contact['public_key']==OTHER,server_timestamp=int(time.time()-state['lag']))
    original=commands.send_cmd
    async def send(contact,command,timestamp=None):
        assert companion.control_lock.locked()
        state['writes'].append(command[3:])
        assert command[3:]=='clock sync'
        state['lag']=0
        if failure: raise failure
        return await original(contact,command,timestamp)
    commands.send_login_sync=login;commands.send_cmd=send
    runtime=NS(companion=companion,control=object(),logger=Mock())
    monkeypatch.setattr(radio,'synchronized_host_time',AsyncMock(side_effect=lambda:int(time.time())))
    monkeypatch.setattr(radio,'TIMESTAMP_GAP',0)
    return radio.ClockSyncWorker(runtime,database.DB_FILE),state


def test_defaults_intervals_revision_persistence_and_independence(station):
    first=store.settings(database.DB_FILE,KEY)
    assert first['enabled']==0 and first['interval_hours']==24 and first['next_due'] is None
    for enabled,interval in [(1,24),(True,2),(True,True),(True,1.5),(True,0)]:
        with pytest.raises(ValueError):store.save(database.DB_FILE,KEY,enabled,interval,0)
    for interval in store.INTERVALS:
        old=store.settings(database.DB_FILE,KEY)
        saved=store.save(database.DB_FILE,KEY,True,interval,old['revision'])
        assert saved['interval_hours']==interval and saved['next_due']>=time.time()+59
    assert store.settings(database.DB_FILE,OTHER)['enabled']==0
    with pytest.raises(ValueError,match='changed'):store.save(database.DB_FILE,KEY,False,24,0)
    assert not (database.DB_FILE.parent/'repeaterStatistics').exists()
    # Reopening the application schema is additive and preserves the schedule.
    station.create_database()
    assert store.settings(database.DB_FILE,KEY)['next_due']==saved['next_due']


def test_behind_clock_uses_acl_and_exact_transport_readback(station,monkeypatch):
    async def run():
        worker,state=fixture_worker(monkeypatch);ready()
        await worker.tick()
        saved=store.settings(database.DB_FILE,KEY)
        assert state['writes']==['clock sync'] and state['logins']==[KEY,KEY]
        assert saved['state']=='synchronized' and saved['last_success'] and not saved['uncertain']
        assert abs(saved['clock_offset'])<2
        assert saved['last_result']['success'] and saved['last_result']['state']=='synchronized'
        changed=store.save(database.DB_FILE,KEY,True,48,saved['revision'])
        assert changed['last_result']==saved['last_result']
        await worker.tick();assert len(state['writes'])==1
    asyncio.run(run())


@pytest.mark.parametrize('lag,state,success',[(0,'verified',True),(4,'verified',True),(-60,'ahead',False)])
def test_within_tolerance_and_ahead_never_write(station,monkeypatch,lag,state,success):
    async def run():
        worker,seen=fixture_worker(monkeypatch,lag=lag);ready();await worker.tick()
        saved=store.settings(database.DB_FILE,KEY)
        assert saved['state']==state and bool(saved['last_success'])==success and not seen['writes']
    asyncio.run(run())


@pytest.mark.parametrize('kind',['admin','identity','unreachable','host','companion_time'])
def test_failed_preconditions_do_not_set_clock(station,monkeypatch,kind):
    async def run():
        worker,seen=fixture_worker(monkeypatch,admin=kind!='admin',bad_identity=kind=='identity');ready()
        if kind=='host':monkeypatch.setattr(radio,'synchronized_host_time',AsyncMock(side_effect=ValueError('Host time not synchronized')))
        if kind=='unreachable':worker.runtime.companion.mc.commands.send_login_sync=AsyncMock(side_effect=asyncio.TimeoutError())
        if kind=='companion_time':worker.runtime.companion.mc.commands.get_time=AsyncMock(return_value=event(EventType.CURRENT_TIME,time=1))
        await worker.tick();saved=store.settings(database.DB_FILE,KEY)
        assert saved['state']=='error' and saved['last_attempt'] and saved['error'] and not saved['last_success']
        assert not seen['writes']
        if kind=='admin':assert 'Administrator authorization unavailable' in saved['error']
    asyncio.run(run())


def test_uncertain_write_is_persistently_fenced_no_automatic_retry(station,monkeypatch):
    async def run():
        worker,seen=fixture_worker(monkeypatch,failure=asyncio.TimeoutError());cfg=ready();await worker.tick()
        saved=store.settings(database.DB_FILE,KEY)
        assert saved['uncertain'] and saved['state']=='verification_required' and saved['next_due'] is None
        assert not store.due(database.DB_FILE,time.time()+30*86400)
        store.recover(database.DB_FILE)
        with pytest.raises(ValueError,match='Manually verify'):store.save(database.DB_FILE,KEY,True,24,cfg['revision'])
        assert len(seen['writes'])==1
        resumed=store.save(database.DB_FILE,KEY,True,24,cfg['revision'],True)
        assert resumed['next_due']>time.time() and not resumed['uncertain']
    asyncio.run(run())


def test_restart_recovers_read_preserves_due_and_write_requires_verification(station):
    cfg=ready();assert store.claim(database.DB_FILE,cfg,time.time())
    due=store.settings(database.DB_FILE,KEY)['next_due'];store.recover(database.DB_FILE)
    assert store.settings(database.DB_FILE,KEY)['state']=='interrupted'
    assert store.settings(database.DB_FILE,KEY)['last_result']['state']=='interrupted'
    assert store.settings(database.DB_FILE,KEY)['next_due']==due
    assert not store.due(database.DB_FILE,time.time())
    assert store.mark_write(database.DB_FILE,cfg);store.recover(database.DB_FILE)
    assert store.settings(database.DB_FILE,KEY)['state']=='verification_required'
    assert not store.due(database.DB_FILE,time.time()+864000)


def test_removal_disables_and_readdition_does_not_reenable(station):
    cfg=ready()
    with station.db:station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(KEY,))
    assert not store.still_enabled(database.DB_FILE,cfg)
    assert not store.due(database.DB_FILE,time.time()+86400)
    with station.db:voltage_store.ensure_repeater(station.db,KEY)
    assert not store.settings(database.DB_FILE,KEY)['enabled']
    assert not store.claim(database.DB_FILE,cfg,time.time())


@pytest.mark.parametrize('action',['disable','remove','disconnect','shutdown'])
def test_pending_reads_cancel_and_release_shared_lock(station,monkeypatch,action):
    async def run():
        worker,seen=fixture_worker(monkeypatch);ready()
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def wait_login(*args,**kw):
            entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        worker.runtime.companion.mc.commands.send_login_sync=wait_login
        task=asyncio.create_task(worker.tick());await entered.wait()
        if action=='disable':
            cfg=store.settings(database.DB_FILE,KEY);store.save(database.DB_FILE,KEY,False,24,cfg['revision'])
        elif action=='remove':
            with station.db:station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(KEY,))
        elif action=='disconnect':worker.runtime.companion.mc.connection_manager.is_connected=False
        else:task.cancel()
        await asyncio.wait_for(asyncio.gather(task,return_exceptions=True),2)
        assert cancelled.is_set() and not worker.runtime.companion.control_lock.locked() and not seen['writes']
    asyncio.run(run())


def test_disconnected_preserves_schedule_and_manual_operation_owns_lock(station,monkeypatch):
    async def run():
        worker,seen=fixture_worker(monkeypatch);cfg=ready();c=worker.runtime.companion
        c.mc.connection_manager.is_connected=False;await worker.tick()
        assert store.settings(database.DB_FILE,KEY)['next_due']==cfg['next_due'] and not seen['logins']
        c.mc.connection_manager.is_connected=True
        async with c.control_lock:
            task=asyncio.create_task(worker.tick());await asyncio.sleep(.05)
            assert not seen['logins']
            old=store.settings(database.DB_FILE,KEY);store.save(database.DB_FILE,KEY,False,24,old['revision'])
        await task;assert not seen['writes']
    asyncio.run(run())


def test_scheduler_startup_pacing_and_close(station,monkeypatch):
    async def run():
        worker,seen=fixture_worker(monkeypatch);ready();ready(OTHER)
        monkeypatch.setattr(radio,'STARTUP_DELAY',.1);monkeypatch.setattr(radio,'CHECK_INTERVAL',.02)
        worker.start();await asyncio.sleep(.05);assert not seen['logins']
        await asyncio.sleep(.4);assert seen['writes']==['clock sync'] # second due repeater is paced, not a burst
        await worker.close();assert worker.task is None and worker.inflight is None
    asyncio.run(run())


def test_host_ntp_check_fails_closed(monkeypatch):
    async def run():
        for output in (b'no\n',b'',b'unknown\n'):
            process=NS(communicate=AsyncMock(return_value=(output,None)),returncode=0)
            monkeypatch.setattr(radio.asyncio,'create_subprocess_exec',AsyncMock(return_value=process))
            with pytest.raises(ValueError,match='NTP'):await radio.synchronized_host_time()
        process=NS(communicate=AsyncMock(return_value=(b'yes\n',None)),returncode=0)
        monkeypatch.setattr(radio.asyncio,'create_subprocess_exec',AsyncMock(return_value=process))
        assert await radio.synchronized_host_time()>1704067200
        monkeypatch.setattr(radio.asyncio,'create_subprocess_exec',AsyncMock(side_effect=FileNotFoundError()))
        with pytest.raises(ValueError,match='unavailable'):await radio.synchronized_host_time()
    asyncio.run(run())


def test_local_api_validation_and_no_radio_access(station):
    from flask import Flask
    from meshcorestation.web.clock_sync_api import register_clock_sync_routes
    app=Flask(__name__);register_clock_sync_routes(app);client=app.test_client()
    url='/api/repeater-clock-sync';headers={'X-Meshcore-Control':'1'}
    assert client.get(url,query_string={'public_key':KEY}).status_code==403
    result=client.get(url,query_string={'public_key':KEY},headers=headers)
    assert result.json['config']['enabled']==0 and result.headers['Cache-Control']=='no-store'
    assert client.post(url,headers={**headers,'Origin':'https://evil.example'},json={}).status_code==403
    assert client.post(url,headers=headers,json=dict(public_key=KEY,enabled=True,interval_hours=2,revision=0)).status_code==400
    saved=client.post(url,headers=headers,json=dict(public_key=KEY,enabled=True,interval_hours=24,revision=0))
    assert saved.json['config']['enabled']==1
    assert client.get(url,headers=headers,query_string={'public_key':'ab'}).status_code==400


@pytest.mark.parametrize('operation',['timeout','disconnect','disable','shutdown','readback'])
def test_write_phase_cancellation_remains_uncertain(station,monkeypatch,operation):
    async def run():
        worker,seen=fixture_worker(monkeypatch);ready()
        entered=asyncio.Event();release=asyncio.Event()
        original=worker.runtime.companion.mc.commands.send_cmd
        async def pending(*args,**kwargs):
            result=await original(*args,**kwargs)
            entered.set()
            await release.wait()
            return result
        worker.runtime.companion.mc.commands.send_cmd=pending
        task=asyncio.create_task(worker.tick());await asyncio.wait_for(entered.wait(),2)
        assert store.settings(database.DB_FILE,KEY)['uncertain']
        if operation=='disable':
            cfg=store.settings(database.DB_FILE,KEY);store.save(database.DB_FILE,KEY,False,24,cfg['revision'])
        elif operation=='disconnect':worker.runtime.companion.mc.connection_manager.is_connected=False
        elif operation=='readback':
            worker.runtime.companion.mc.commands.send_login_sync=AsyncMock(side_effect=asyncio.TimeoutError());release.set()
        else:task.cancel()
        await asyncio.wait_for(asyncio.gather(task,return_exceptions=True),2)
        saved=store.settings(database.DB_FILE,KEY)
        assert saved['uncertain'] and not saved['last_success'] and not store.due(database.DB_FILE,time.time()+10**7)
        assert not worker.runtime.companion.control_lock.locked() and seen['writes']==['clock sync']
        store.recover(database.DB_FILE)
        assert store.settings(database.DB_FILE,KEY)['uncertain']
    asyncio.run(run())


def test_discontinuous_and_invalid_host_clock_rejected(monkeypatch):
    monkeypatch.setattr(radio,'host_time',Mock(side_effect=RuntimeError('Pi clock is invalid')))
    with pytest.raises(RuntimeError,match='invalid'):asyncio.run(radio.synchronized_host_time())
    with pytest.raises(ValueError,match='Host clock changed'):
        radio.ClockSyncWorker.check_elapsed(time.time(),time.time()+50,time.monotonic())


def test_manual_sync_clock_action_remains_available(station):
    from meshcorestation.radio.repeater_control import RepeaterControl
    async def run():
        companion=NS(mc=FakeMeshCore(),database=station)
        sent=[];original=companion.mc.commands.send_cmd
        async def capture(contact,command,**kwargs):
            sent.append(command[3:]);return await original(contact,command,**kwargs)
        companion.mc.commands.send_cmd=capture
        control=RepeaterControl(companion)
        login=await control.execute(dict(action='login',public_key=KEY,password='admin'))
        result=await control.execute(dict(action='action',public_key=KEY,session=login['session'],name='clock_sync',confirm=True))
        assert result['ok'] and len(sent)==1 and sent[0].startswith('time ')
        assert not store.settings(database.DB_FILE,KEY)['enabled']
    asyncio.run(run())


def test_failure_of_one_repeater_does_not_block_another(station,monkeypatch):
    async def run():
        worker,seen=fixture_worker(monkeypatch,admin=False);ready();ready(OTHER)
        monkeypatch.setattr(radio,'ATTEMPT_GAP',0)
        await worker.tick();await worker.tick()
        assert store.settings(database.DB_FILE,KEY)['state']=='error'
        assert store.settings(database.DB_FILE,OTHER)['state']=='synchronized'
        assert seen['writes']==['clock sync']
    asyncio.run(run())


def test_latency_limited_comparison_does_not_claim_success_or_write(station,monkeypatch):
    async def run():
        worker,seen=fixture_worker(monkeypatch,lag=7);cfg=ready();now=time.time()
        # Model a slow login round trip without making this test wait 14 seconds.
        samples=iter([now,now-14,now])
        monkeypatch.setattr(radio,'time',NS(time=lambda:next(samples),monotonic=time.monotonic))
        monkeypatch.setattr(worker,'check_elapsed',lambda *args:None)
        await worker.attempt(cfg,worker.runtime.companion)
        saved=store.settings(database.DB_FILE,KEY)
        assert saved['state']=='latency_uncertain' and not saved['last_success']
        assert not seen['writes'] and saved['last_result']['latency_allowance_seconds']==14
    asyncio.run(run())


def test_database_fence_failure_prevents_transmission(station,monkeypatch):
    import sqlite3
    async def run():
        worker,seen=fixture_worker(monkeypatch);ready()
        monkeypatch.setattr(store,'mark_write',Mock(side_effect=sqlite3.OperationalError('database full')))
        await worker.tick()
        saved=store.settings(database.DB_FILE,KEY)
        assert not seen['writes'] and not saved['uncertain'] and saved['state']=='error'
        assert 'database full' in saved['error']
    asyncio.run(run())


def test_cancellation_drains_the_persistent_write_fence(station,monkeypatch):
    from threading import Event
    async def run():
        worker,seen=fixture_worker(monkeypatch);ready()
        entered,release=Event(),Event();original=store.mark_write
        def blocked(*args):
            result=original(*args);entered.set();assert release.wait(2);return result
        monkeypatch.setattr(store,'mark_write',blocked)
        task=asyncio.create_task(worker.tick());assert await asyncio.to_thread(entered.wait,2)
        task.cancel();release.set();await asyncio.gather(task,return_exceptions=True)
        saved=store.settings(database.DB_FILE,KEY)
        assert saved['uncertain'] and saved['state']=='verification_required' and not seen['writes']
        assert not worker.runtime.companion.control_lock.locked()
    asyncio.run(run())


def test_startup_database_failure_recovers_without_losing_worker(station,monkeypatch):
    import sqlite3
    async def run():
        worker,seen=fixture_worker(monkeypatch);ready();original=store.recover;calls=[]
        def recover(path):
            calls.append(path)
            if len(calls)==1:raise sqlite3.OperationalError('database is locked')
            return original(path)
        monkeypatch.setattr(store,'recover',recover)
        monkeypatch.setattr(radio,'STARTUP_DELAY',0);monkeypatch.setattr(radio,'CHECK_INTERVAL',.02)
        worker.start()
        for _ in range(50):
            if seen['writes']:break
            await asyncio.sleep(.02)
        assert len(calls)==2 and seen['writes']==['clock sync'] and not worker.task.done()
        await worker.close()
    asyncio.run(run())
