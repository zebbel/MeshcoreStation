"""Explicit one-time grants, fake transport only; no actual mesh packets."""
import asyncio
from contextlib import closing
import sqlite3
import time
from unittest.mock import AsyncMock
import pytest
from meshcorestation import config
from meshcorestation.bridge import bridge
from meshcorestation.storage import database,neighbor_snr as legacy,neighbor_snr_manual as manual,averaged_snr as aggregates,passive_stats
from meshcorestation.storage.connection import connect
from meshcorestation.radio import averaged_snr_collection as collection
from test_averaged_snr import station,A,B,C,response,handler_for,monitor_fixture


def settings(enabled):
    cfg=legacy.save_settings(database.DB_FILE,A,enabled,47)
    if enabled:
        with closing(connect(database.DB_FILE)) as db,db:db.execute('UPDATE neighbor_monitor SET next_due=? WHERE public_key=?',(time.time()+600,A))
    return legacy.settings(database.DB_FILE,A)


@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('protocol',['averaged','legacy'])
def test_one_time_read_preserves_every_automatic_setting(station,monkeypatch,enabled,protocol):
    async def run():
        before=settings(enabled)
        if protocol=='averaged':handler=handler_for([response()])
        else:
            async def handler(payload):return None
        worker,_,old=monitor_fixture(monkeypatch,handler)
        job=manual.enqueue(database.DB_FILE,A);assert job['state']=='queued'
        await worker.tick();result=manual.snapshot(database.DB_FILE,A)['job']
        assert result['state']=='complete' and result['records']==1 and result['protocol']==protocol
        assert not manual.snapshot(database.DB_FILE,A)['busy'] and result['pages']>=1
        assert legacy.settings(database.DB_FILE,A)==before
        assert bool(old)==(protocol=='legacy')
        path=passive_stats.statistics_path(database.DB_FILE,A)
        with closing(sqlite3.connect(path)) as db:
            table='neighbor_snr_aggregates' if protocol=='averaged' else 'neighbor_snr_readings'
            assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==1
        # The grant is spent: saved job IDs do not authorize any more observations.
        forged=dict(before,manual_job_id=job['job_id'])
        assert not legacy.still_enabled(database.DB_FILE,forged)
    asyncio.run(run())


def test_manual_does_not_consume_due_automatic_collection(station,monkeypatch):
    async def run():
        legacy.save_settings(database.DB_FILE,A,True,30)
        with closing(connect(database.DB_FILE)) as db,db:db.execute('UPDATE neighbor_monitor SET next_due=0 WHERE public_key=?',(A,))
        before=legacy.settings(database.DB_FILE,A)
        worker,_,_=monitor_fixture(monkeypatch,handler_for([response()]))
        manual.enqueue(database.DB_FILE,A);await worker.tick()
        assert legacy.settings(database.DB_FILE,A)==before
        await worker.tick();assert legacy.settings(database.DB_FILE,A)['next_due']>time.time()
    asyncio.run(run())


def test_partial_manual_read_continues_and_deduplicates(station,monkeypatch):
    async def run():
        before=settings(False);rows=[response(seq=i,window=i-1,ceiling=2) for i in (1,2)]
        worker,calls,_=monitor_fixture(monkeypatch,handler_for(rows));monkeypatch.setattr(collection,'MAX_RECORDS',1)
        manual.enqueue(database.DB_FILE,A);await worker.tick()
        first=manual.snapshot(database.DB_FILE,A)['job'];assert first['state']=='partial' and first['records']==1
        assert aggregates.status(database.DB_FILE,A)['pending'] and len(calls)==2
        manual.enqueue(database.DB_FILE,A);await worker.tick()
        assert manual.snapshot(database.DB_FILE,A)['job']['state']=='complete' and len(calls)==3
        assert not aggregates.status(database.DB_FILE,A)['pending']
        manual.enqueue(database.DB_FILE,A);await worker.tick() # no new completed windows
        assert manual.snapshot(database.DB_FILE,A)['job']['records']==0
        with closing(sqlite3.connect(passive_stats.statistics_path(database.DB_FILE,A))) as db:
            assert db.execute('SELECT COUNT(*) FROM neighbor_snr_aggregates').fetchone()[0]==2
        assert legacy.settings(database.DB_FILE,A)==before
    asyncio.run(run())


def test_legacy_repeated_last_heard_response_remains_one_measurement(station,monkeypatch):
    async def run():
        settings(False)
        async def handler(payload):return None
        worker,_,_=monitor_fixture(monkeypatch,handler)
        for _ in range(2):manual.enqueue(database.DB_FILE,A);await worker.tick()
        with closing(sqlite3.connect(passive_stats.statistics_path(database.DB_FILE,A))) as db:
            assert db.execute('SELECT COUNT(*) FROM neighbor_snr_readings').fetchone()[0]==2
            assert db.execute('SELECT COUNT(*) FROM neighbor_snr_measurements').fetchone()[0]==1
    asyncio.run(run())


def test_duplicate_requests_and_scheduled_claims_cannot_overlap(station,monkeypatch):
    async def run():
        cfg=settings(True);entered=asyncio.Event();release=asyncio.Event();normal=handler_for([response()])
        async def handler(payload):entered.set();await release.wait();return await normal(payload)
        worker,_,_=monitor_fixture(monkeypatch,handler)
        manual.enqueue(database.DB_FILE,A)
        with pytest.raises(manual.Busy):manual.enqueue(database.DB_FILE,A)
        assert not legacy.claim(database.DB_FILE,cfg,time.time()+10000)
        task=asyncio.create_task(worker.tick());await entered.wait()
        assert worker.collection_lock.locked() and worker.runtime.companion.control_lock.locked()
        with pytest.raises(manual.Busy):manual.enqueue(database.DB_FILE,A)
        release.set();await task
        assert not worker.collection_lock.locked() and not worker.runtime.companion.control_lock.locked()
    asyncio.run(run())


@pytest.mark.parametrize('reason',['timeout','disconnect','remove','shutdown'])
def test_failures_revoke_one_time_grants_without_automatic_replay(station,monkeypatch,reason):
    async def run():
        before=settings(False);entered=asyncio.Event()
        # A known protocol timeout must not silently turn into a legacy request.
        with closing(connect(database.DB_FILE)) as db,db:
            db.execute("INSERT INTO neighbor_snr_protocol(public_key,capability,probe_after) VALUES(?,'averaged',?)",(A,time.time()+10000))
        async def handler(payload):
            entered.set()
            if reason=='timeout':return None
            await asyncio.Event().wait()
        worker,calls,_=monitor_fixture(monkeypatch,handler);job=manual.enqueue(database.DB_FILE,A)
        task=asyncio.create_task(worker.tick());await entered.wait()
        if reason=='disconnect':worker.runtime.companion.mc.connection_manager.is_connected=False
        elif reason=='remove':
            with station.db:station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(A,))
        elif reason=='shutdown':task.cancel()
        await asyncio.wait_for(asyncio.gather(task,return_exceptions=True),2)
        if reason!='remove':
            result=manual.snapshot(database.DB_FILE,A)['job']
            assert result['state'] in ('error','interrupted','partial') and result['error']
            assert legacy.settings(database.DB_FILE,A)==before
            assert not legacy.still_enabled(database.DB_FILE,dict(before,manual_job_id=job['job_id']))
        else:
            row=station.db.execute('SELECT state,error FROM neighbor_snr_manual WHERE public_key=?',(A,)).fetchone()
            assert row['state']=='cancelled' and 'removed' in row['error']
        assert len(calls)==1 and not worker.runtime.companion.control_lock.locked()
        if reason!='remove':await worker.tick();assert len(calls)==1 # no manual retry
    asyncio.run(run())


def test_arbitrary_or_finished_job_ids_never_bypass_disabled_monitoring(station):
    before=settings(False)
    forged=dict(before,manual_job_id='00'*16)
    assert not legacy.still_enabled(database.DB_FILE,forged)
    assert not aggregates.record(database.DB_FILE,forged,'forged',time.time(),{'record':None},b'')
    assert not passive_stats.statistics_path(database.DB_FILE,A).exists()
    job=manual.enqueue(database.DB_FILE,A);cfg=manual.claim(database.DB_FILE,job)
    assert cfg and legacy.still_enabled(database.DB_FILE,cfg)
    manual.finish(database.DB_FILE,cfg)
    assert not legacy.still_enabled(database.DB_FILE,cfg)


def test_restart_expiry_and_unmanaged_validation(station):
    settings(False)
    with pytest.raises(ValueError):manual.enqueue(database.DB_FILE,B)
    with pytest.raises(ValueError):manual.enqueue(database.DB_FILE,'ab')
    job=manual.enqueue(database.DB_FILE,A)
    manual.cancel_pending(database.DB_FILE,'Collector restarted; request a new read explicitly.')
    assert manual.pending(database.DB_FILE) is None
    assert manual.snapshot(database.DB_FILE,A)['job']['state']=='interrupted'
    manual.enqueue(database.DB_FILE,A)
    with station.db:station.db.execute('UPDATE neighbor_snr_manual SET expires_at=0')
    assert manual.pending(database.DB_FILE) is None
    assert manual.snapshot(database.DB_FILE,A)['job']['state']=='cancelled'


def test_fast_local_api_and_duplicate_submission(station,monkeypatch):
    from flask import Flask
    from meshcorestation.web.neighbor_snr_manual_api import register_manual_snr_routes
    async def run():
        before=settings(False);worker,_,_=monitor_fixture(monkeypatch,handler_for([response()]))
        runtime=worker.runtime;runtime.neighbor_monitor=worker
        idle=asyncio.create_task(asyncio.Event().wait());worker.task=idle;worker.ready=True;bridge.attach(runtime)
        app=Flask(__name__);register_manual_snr_routes(app);client=app.test_client();url='/api/repeater-statistics/read-now';headers={'X-Meshcore-Control':'1'}
        try:
            assert client.post(url,json={'public_key':A}).status_code==403
            assert client.post(url,headers={**headers,'Origin':'https://other.invalid'},json={'public_key':A}).status_code==403
            assert client.post(url,headers=headers,json={'public_key':A,'enabled':True}).status_code==400
            assert client.post(url,headers=headers,json={'public_key':B}).status_code==400
            start=time.monotonic();result=client.post(url,headers=headers,json={'public_key':A})
            assert result.status_code==202 and time.monotonic()-start<.5
            assert result.json['job']['state']=='queued' and result.headers['Cache-Control']=='no-store'
            duplicate=client.post(url,headers=headers,json={'public_key':A});assert duplicate.status_code==409
            assert duplicate.json['job']['job_id']==result.json['job']['job_id']
            await worker.tick()
            status_reply=client.get(url,headers=headers,query_string={'public_key':A})
            assert status_reply.json['job']['state']=='complete' and status_reply.json['job']['records']==1
            assert legacy.settings(database.DB_FILE,A)==before
            runtime.companion.mc.connection_manager.is_connected=False
            assert client.post(url,headers=headers,json={'public_key':A}).status_code==503
        finally:
            bridge.detach();idle.cancel();await asyncio.gather(idle,return_exceptions=True);worker.task=None
    asyncio.run(run())


def test_existing_scheduler_wakes_promptly_for_manual_work(station,monkeypatch):
    async def run():
        before=settings(False);worker,_,_=monitor_fixture(monkeypatch,handler_for([response()]))
        idle=asyncio.Event();original=worker.tick
        async def tick():await original();idle.set()
        monkeypatch.setattr(worker,'tick',tick);worker.start()
        await asyncio.wait_for(idle.wait(),1)
        manual.enqueue(database.DB_FILE,A);worker.wakeup.set()
        for _ in range(50):
            if manual.snapshot(database.DB_FILE,A)['job']['state']=='complete':break
            await asyncio.sleep(.01)
        assert manual.snapshot(database.DB_FILE,A)['job']['state']=='complete'
        assert legacy.settings(database.DB_FILE,A)==before
        await worker.close()
    asyncio.run(run())


def test_cancellation_after_commit_preserves_count_and_revokes_grant(station,monkeypatch):
    async def run():
        settings(False);worker,_,_=monitor_fixture(monkeypatch,handler_for([response()]))
        original=aggregates.record
        # The callback executes on a DB thread; use a separate connection there.
        def remove_on_thread(*args,**kwargs):
            value=original(*args,**kwargs)
            if args[4]['record']:
                with closing(connect(database.DB_FILE)) as db,db:db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(A,))
            return value
        monkeypatch.setattr(aggregates,'record',remove_on_thread)
        manual.enqueue(database.DB_FILE,A);await worker.tick()
        row=station.db.execute('SELECT state,records FROM neighbor_snr_manual WHERE public_key=?',(A,)).fetchone()
        assert row['state']=='cancelled' and row['records']==1
    asyncio.run(run())


def test_startup_recovery_failure_cannot_replay_a_persisted_manual_request(station,monkeypatch):
    async def run():
        settings(False);worker,calls,_=monitor_fixture(monkeypatch,handler_for([response()]))
        manual.enqueue(database.DB_FILE,A);failed=asyncio.Event();recovered=asyncio.Event();loop=asyncio.get_running_loop()
        original=manual.cancel_pending;attempts=[]
        def recover(path,reason):
            attempts.append(reason)
            if len(attempts)==1:
                loop.call_soon_threadsafe(failed.set)
                raise sqlite3.OperationalError('database locked')
            return original(path,reason)
        original_tick=worker.tick
        async def tick():await original_tick();recovered.set()
        monkeypatch.setattr(manual,'cancel_pending',recover);monkeypatch.setattr(worker,'tick',tick)
        worker.start();await asyncio.wait_for(failed.wait(),1)
        assert not worker.ready and not calls
        worker.wakeup.set();await asyncio.wait_for(recovered.wait(),1)
        assert worker.ready and not calls and manual.snapshot(database.DB_FILE,A)['job']['state']=='interrupted'
        await worker.close()
    asyncio.run(run())


def test_status_database_failure_does_not_block_collector_shutdown(station,monkeypatch):
    async def run():
        settings(False);worker,_,_=monitor_fixture(monkeypatch,handler_for([response()]))
        def unavailable(*args):raise sqlite3.OperationalError('database unavailable')
        monkeypatch.setattr(manual,'cancel_pending',unavailable)
        await worker.close()
        assert worker.task is None and not worker.ready
        worker.runtime.logger.warning.assert_called_once()
    asyncio.run(run())
