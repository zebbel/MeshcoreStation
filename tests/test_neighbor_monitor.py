"""Synthetic neighbor monitoring only; no serial port or mesh traffic."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace as NS
from unittest.mock import Mock,AsyncMock
import pytest
from meshcorestation import config
from meshcorestation.storage import database,voltage_store,neighbor_snr as store,passive_stats
from meshcorestation.radio.neighbor_names import with_neighbor_names
from meshcorestation.radio import neighbor_monitor as radio
from meshcorestation.storage.statistics_view import aggregate

A='aa11'+'01'*30
B='bb22'+'02'*30
C='cc33'+'03'*30

@pytest.fixture
def station(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_FILE',tmp_path/'meshcorestation.db');monkeypatch.setattr(config,'DB_PATH',database.DB_FILE)
    owner=database.Database(Mock())
    for key,name in [(A,'Managed'),(B,'Unmanaged neighbor'),(C,'Other neighbor')]:
        owner.add_new_repeater(NS(payload=dict(type=2,public_key=key,adv_name=name)),observed=False)
    with owner.db:voltage_store.ensure_repeater(owner.db,A)
    yield owner
    owner.close()


def test_names_resolve_full_keys_and_preserve_uncertain_prefixes(station):
    station.add_new_repeater(NS(payload=dict(type=2,public_key='bb99'+'05'*30,adv_name='Collision')),observed=False)
    rows=with_neighbor_names(station.db,dict(neighbours=[dict(pubkey='bb22'),dict(pubkey='bb'),dict(pubkey='ffff')]))['neighbours']
    assert rows[0]['public_key']==B and rows[0]['name']=='Unmanaged neighbor'
    assert rows[1]['resolution']=='ambiguous' and rows[1]['name']=='Ambiguous repeater (bb…)'
    assert rows[2]['resolution']=='unknown' and rows[2]['name']=='Unknown Repeater (ffff…)'
    assert 'public_key' not in rows[1] and 'public_key' not in rows[2]


def test_settings_default_validation_persistence_and_membership(station):
    path=database.DB_FILE
    assert not store.settings(path,A)['enabled'] and store.settings(path,A)['interval_minutes']==30
    assert not passive_stats.statistics_path(path,A).exists()
    for enabled,interval in [(True,0),(True,4),(True,1441),(1,30),(True,5.5)]:
        with pytest.raises(ValueError):store.save_settings(path,A,enabled,interval)
    with pytest.raises(ValueError):store.save_settings(path,B,True,30)
    first=store.save_settings(path,A,True,30)
    assert store.settings(path,A)['enabled']==1
    assert store.claim(path,first,first['next_due'])
    assert not store.claim(path,first,first['next_due']+1)
    assert not store.due(path,first['next_due']+1799) # restart preserves claim schedule
    store.save_settings(path,A,False,30)
    assert not store.still_enabled(path,first)
    assert not passive_stats.statistics_path(path,A).exists()


def test_raw_polls_dedup_distinct_samples_invalid_values_and_periods(station):
    cfg=store.save_settings(database.DB_FILE,A,True,30)
    def record(poll,start,age,snr=3,prefix='bb22'):
        assert store.record_page(database.DB_FILE,cfg,poll,start,start+2,[dict(pubkey=prefix,snr=snr,secs_ago=age)])
    record('first',10000,10);record('same',11800,1810) # same event, aged by 30 min
    record('new',13600,5,5);record('invalid',13605,2,None);record('age',13605,None,4)
    record('unknown',13600,5,1,'ffff')
    path=passive_stats.statistics_path(database.DB_FILE,A)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM neighbor_snr_readings').fetchone()[0]==6
        assert db.execute('SELECT COUNT(*) FROM neighbor_snr_measurements').fetchone()[0]==3
    view=aggregate(database.DB_FILE,A,1,now=14000)
    rows=view['neighbor_snr'];known=next(r for r in rows if r['public_key']==B)
    assert known['samples']==2 and known['average_snr']==4 and known['name']=='Unmanaged neighbor'
    assert any(r['resolution']=='unknown' and r['samples']==1 for r in rows)
    assert view['totals']['receptions']==0 # active readings are not passive traffic
    store.save_settings(database.DB_FILE,A,False,30)
    assert not store.record_page(database.DB_FILE,cfg,'disabled',14000,14001,[])
    assert aggregate(database.DB_FILE,A,7,now=14000)['neighbor_snr']==rows
    # A stale reading first discovered now is filtered by source observation age.
    cfg=store.save_settings(database.DB_FILE,A,True,30)
    store.record_page(database.DB_FILE,cfg,'old',300000,300002,[dict(pubkey='cc33',snr=10,secs_ago=200000)])
    assert not aggregate(database.DB_FILE,A,1,now=300010)['neighbor_snr']
    assert any(r['public_key']==C for r in aggregate(database.DB_FILE,A,7,now=300010)['neighbor_snr'])
    with station.db:station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(A,))
    assert not store.record_page(database.DB_FILE,cfg,'removed',300010,300012,[])
    assert path.exists() and not passive_stats.statistics_path(database.DB_FILE,B).exists()


def test_ambiguity_not_upgraded_and_registry_collisions_checked(station):
    cfg=store.save_settings(database.DB_FILE,A,True,30)
    store.record_page(database.DB_FILE,cfg,'first',100,102,[dict(pubkey='bb',snr=2,secs_ago=5)])
    station.add_new_repeater(NS(payload=dict(type=2,public_key='bb99'+'05'*30,adv_name='Collision')),observed=False)
    store.record_page(database.DB_FILE,cfg,'second',120,122,[dict(pubkey='bb',snr=4,secs_ago=5)])
    rows=aggregate(database.DB_FILE,A,1,now=150)['neighbor_snr']
    assert rows and all(r['public_key'] is None and r['resolution']=='ambiguous' for r in rows)


def test_scheduler_pages_locking_disconnect_failures_and_disable(station,monkeypatch):
    async def scenario():
        cfg=store.save_settings(database.DB_FILE,A,True,30)
        lock=asyncio.Lock();seen=[]
        async def request(contact,**kw):
            assert lock.locked();seen.append(kw['offset'])
            entries=[dict(pubkey='bb22',snr=3,secs_ago=5),dict(pubkey='cc33',snr=4,secs_ago=6),dict(pubkey='ffff',snr=2,secs_ago=5)]
            rows=entries[kw['offset']:kw['offset']+2]
            return dict(pubkey_prefix=A[:12],neighbours=rows,results_count=len(rows),neighbours_count=3)
        companion=NS(control_lock=lock,mc=NS(connection_manager=NS(is_connected=True),commands=NS(req_neighbours_sync=request)))
        runtime=NS(companion=companion,control=object(),logger=Mock())
        prepare=NS(contact=AsyncMock(return_value={'public_key':A}),login=AsyncMock(return_value={}))
        monkeypatch.setattr(radio,'RepeaterTransport',lambda c:prepare);monkeypatch.setattr(radio,'PAGE_SIZE',2);monkeypatch.setattr(radio,'REQUEST_GAP',0)
        worker=radio.NeighborMonitor(runtime,database.DB_FILE)
        await worker.tick();assert seen==[0,2] and prepare.login.await_count==1
        assert store.settings(database.DB_FILE,A)['state']=='waiting'
        await worker.tick();assert seen==[0,2] # not due, never immediate retry
        cfg=store.save_settings(database.DB_FILE,A,True,30)
        companion.mc.connection_manager.is_connected=False
        await worker.tick();assert store.settings(database.DB_FILE,A)['last_attempt'] is not None and seen==[0,2]
        companion.mc.connection_manager.is_connected=True
        async def timeout(*a,**kw):raise asyncio.TimeoutError()
        companion.mc.commands.req_neighbours_sync=timeout
        await worker.tick();assert store.settings(database.DB_FILE,A)['state']=='error'
        await worker.tick();assert prepare.login.await_count==2
        cfg=store.save_settings(database.DB_FILE,A,True,30)
        async def disable(contact,**kw):
            store.save_settings(database.DB_FILE,A,False,30)
            return dict(pubkey_prefix=A[:12],neighbours=[dict(pubkey='bb22',snr=9,secs_ago=0)],results_count=1,neighbours_count=20)
        companion.mc.commands.req_neighbours_sync=disable
        await worker.tick();assert not store.settings(database.DB_FILE,A)['enabled']
        assert not lock.locked()
    asyncio.run(scenario())


def test_monitor_settings_api_guard_and_no_radio(station):
    from flask import Flask
    from meshcorestation.web.statistics_api import register_statistics_routes
    app=Flask(__name__);register_statistics_routes(app);client=app.test_client()
    url='/api/repeater-statistics/neighbor-monitor'
    assert client.post(url,json=dict(public_key=A,enabled=True,interval_minutes=30)).status_code==403
    headers={'X-Meshcore-Control':'1'}
    assert client.get(url+'?public_key='+A,headers=headers).json['config']['enabled']==0
    assert client.post(url,headers=headers,json=dict(public_key=A,enabled=True,interval_minutes=30)).json['config']['enabled']==1
    assert client.post(url,headers=headers,json=dict(public_key=B,enabled=True,interval_minutes=30)).status_code==400
    assert not passive_stats.statistics_path(database.DB_FILE,A).exists()


def test_shutdown_cancels_request_releases_lock_and_preserves_cooldown(station,monkeypatch):
    async def scenario():
        store.save_settings(database.DB_FILE,A,True,30)
        entered=asyncio.Event();lock=asyncio.Lock()
        async def request(*a,**kw):entered.set();await asyncio.Event().wait()
        companion=NS(control_lock=lock,mc=NS(connection_manager=NS(is_connected=True),commands=NS(req_neighbours_sync=request)))
        runtime=NS(companion=companion,control=object(),logger=Mock())
        monkeypatch.setattr(radio,'RepeaterTransport',lambda c:NS(contact=AsyncMock(return_value={'public_key':A}),login=AsyncMock()))
        monkeypatch.setattr(radio,'REQUEST_GAP',0)
        worker=radio.NeighborMonitor(runtime,database.DB_FILE);worker.start()
        await asyncio.wait_for(entered.wait(),2);await worker.close()
        assert not lock.locked() and worker.task is None
        assert store.settings(database.DB_FILE,A)['state']=='error'
        assert not store.due(database.DB_FILE,__import__('time').time())
    asyncio.run(scenario())


def test_queued_request_rechecks_disable_and_membership_generation(station,monkeypatch):
    cfg=store.save_settings(database.DB_FILE,A,True,30)
    with station.db:
        station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(A,))
        voltage_store.ensure_repeater(station.db,A)
    assert not store.still_enabled(database.DB_FILE,cfg)
    assert not store.record_page(database.DB_FILE,cfg,'old-membership',100,102,[dict(pubkey='bb22',secs_ago=1,snr=1)])
    async def scenario():
        cfg=store.save_settings(database.DB_FILE,A,True,30);lock=asyncio.Lock();await lock.acquire()
        prepare=NS(contact=AsyncMock(),login=AsyncMock())
        companion=NS(control_lock=lock,mc=NS(connection_manager=NS(is_connected=True)))
        runtime=NS(companion=companion,control=object(),logger=Mock())
        monkeypatch.setattr(radio,'RepeaterTransport',lambda c:prepare);monkeypatch.setattr(radio,'REQUEST_GAP',0)
        worker=radio.NeighborMonitor(runtime,database.DB_FILE)
        task=asyncio.create_task(worker.poll(cfg))
        for _ in range(20):
            await asyncio.sleep(.01)
            if store.settings(database.DB_FILE,A)['state']=='collecting':break
        store.save_settings(database.DB_FILE,A,False,30);lock.release();await task
        assert prepare.contact.await_count==prepare.login.await_count==0
    asyncio.run(scenario())
