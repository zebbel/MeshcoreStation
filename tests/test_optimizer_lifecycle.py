"""Optimizer lifecycle must erase its data without damaging shared statistics."""
import asyncio
import sqlite3
import time
from contextlib import closing
from types import SimpleNamespace
import pytest
from flask import Flask
from meshcorestation.storage import optimizer_store as store, passive_stats as stats, advisor_history as history
from meshcorestation.web.optimizer_api import register_optimizer_routes
from meshcorestation.radio.repeater_control import RepeaterControl

KEY='ab'*32
OTHER='cd'*32
HEADERS={'X-Meshcore-Control':'1'}

@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'FILE',tmp_path/'optimizer.db')
    monkeypatch.setattr(stats,'STATS_PATH',tmp_path/'statistics.db')
    monkeypatch.setattr(history,'FILE',tmp_path/'history.db')
    monkeypatch.setattr(stats,'known_repeaters',lambda:[{'public_key':KEY,'name':'Hill'}])
    store.initialize();stats.initialize()
    stats.track(KEY)
    for key in (KEY,OTHER):
        store.update_profile(key,'local','12h')
        store.save_neighbors(key,{'neighbours':[],'neighbours_count':0})
        ident=history.begin(key,'flood.max','32','16');history.finish(ident,'16','verified')
    with closing(stats.connect()) as db, db:
        db.execute("INSERT INTO observations(target,at,kind,scoped,ambiguous,first_hop,middle_hop,last_hop,route,previous,following) VALUES(?, ?,5,0,0,1,0,1,'[]','[]','[]')",(KEY,time.time()))
        db.execute("INSERT INTO network_observations(at,kind,scoped,path_len,hash_size,route) VALUES(?,5,0,1,1,'ab')",(time.time(),))
        db.execute('INSERT INTO network_daily VALUES(1,5,0,3)')
    return tmp_path


def counts():
    with closing(stats.connect()) as db:
        return tuple(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                     for table in ('network_observations','network_daily','observations','subscriptions'))


def test_disable_erases_all_optimizer_data_but_keeps_general_statistics(database):
    assert store.status()['enabled']
    state=store.set_enabled(False)
    assert not state['enabled'] and state['since']>0
    assert counts()==(0,0,1,1)
    for key in (KEY,OTHER):
        assert store.profile(key)['polling']=='manual'
        assert store.profile(key)['role']=='unknown'
        assert store.snapshots(key)==[]
        assert history.recent(key)==[]
    assert store.due(time.time()+86400) is None
    assert not store.claim_poll(KEY)
    assert store.save_neighbors(KEY,{'neighbours':[]}) is None
    assert history.begin(KEY,'flood.max','32','16') is None
    with pytest.raises(ValueError,match='disabled'):
        store.update_profile(KEY,'local','12h')
    store.initialize()  # Restart/migration does not re-enable.
    assert not store.status()['enabled']
    assert store.set_enabled(False)==state
    assert store.set_enabled(True)['enabled']
    assert counts()==(0,0,1,1)
    assert store.profile(KEY)['polling']=='manual'


def test_clear_rejects_inflight_reads_and_preserves_storage_limits(database):
    before=time.time()
    old_id=history.begin(KEY,'flood.max','32','16')
    config={**store.DEFAULTS,'budget_mb':4096};store.update_config(config)
    state=store.reset()
    assert state['enabled'] and counts()==(0,0,1,1)
    assert store.config()==config
    store.update_profile(KEY,'local','manual')
    store.poll_error(KEY,'old failure',started_at=before)
    assert store.profile(KEY)['last_error']==''
    assert store.save_neighbors(KEY,{'neighbours':[]},started_at=before) is None
    assert store.save_neighbors(KEY,{'neighbours':[]},started_at=time.time()) is not None
    new_id=history.begin(KEY,'flood.max','64','32')
    assert new_id!=old_id
    history.finish(old_id,'16','verified')
    assert history.recent(KEY)[0]['status']=='pending / outcome unknown'


def test_disabled_collector_keeps_general_statistics_and_rejects_old_queue(database):
    store.set_enabled(False)
    packet=stats.normalize({'route_type':1,'payload_type':5,'path_len':1,'path_hash_size':1,'path':'ab','pkt_payload':b'data'})
    worker=stats.Collector()
    # Run one batch synchronously and terminate as soon as the queue is empty.
    worker.queue.put((time.time(),packet));worker.stop.set();worker.run()
    assert counts()==(0,0,2,1)
    old=time.time()
    store.set_enabled(True)
    worker=stats.Collector();worker.queue.put((old,packet));worker.queue.put((time.time(),packet))
    worker.stop.set();worker.run()
    assert counts()==(1,1,4,1)
    assert not worker.error


def test_removed_downtime_table_migrates_and_old_action_rejected(database):
    with closing(store.connect()) as db, db:
        db.execute('CREATE TABLE downtime (id INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO downtime VALUES(1)')
    store.initialize()
    with closing(store.connect()) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='downtime'").fetchone()
    app=Flask(__name__);register_optimizer_routes(app)
    assert app.test_client().post('/api/repeater-optimizer',headers=HEADERS,
        json={'action':'downtime','public_key':KEY}).status_code==400


def test_api_confirmation_origin_validation_disabled_review_and_clear(database):
    app=Flask(__name__);register_optimizer_routes(app);client=app.test_client()
    url='/api/repeater-optimizer/settings'
    assert client.get(url).status_code==403
    assert client.post(url,headers={**HEADERS,'Origin':'https://evil.test'},json={'action':'clear','confirm':True}).status_code==403
    for payload in [{'action':'clear'},{'action':'enabled','enabled':False},
                    {'action':'enabled','enabled':1},{'action':'unknown'},[]]:
        assert client.post(url,headers=HEADERS,json=payload).status_code==400
    assert counts()==(1,1,1,1)
    assert client.post(url,headers=HEADERS,json={'action':'clear','confirm':True}).json['enabled']
    assert counts()==(0,0,1,1)
    assert client.post(url,headers=HEADERS,json={'action':'enabled','enabled':False,'confirm':True}).json['enabled'] is False
    assert client.get('/api/repeater-optimizer?public_key='+KEY,headers=HEADERS).json['enabled'] is False
    assert client.post('/api/repeater-optimizer',headers=HEADERS,json={'action':'review','public_key':KEY}).status_code==409
    assert client.post(url,headers=HEADERS,json={'action':'enabled','enabled':True}).json['enabled']
    data=client.get('/api/repeater-optimizer?public_key='+KEY,headers=HEADERS).json
    assert data['ok'] and data['statistics']['copies']==0 and not data['history']


def test_disabled_optimizer_radio_operations_rejected_before_transport(database):
    store.set_enabled(False)
    controller=RepeaterControl(SimpleNamespace())
    for payload in ({'action':'advisor_write'}, {'action':'neighbors','optimizer':True}, {'action':'read','optimizer':True}):
        with pytest.raises(ValueError,match='disabled'):
            asyncio.run(controller.execute({**payload,'public_key':KEY}))


def test_reset_during_analysis_discards_stale_response(database,monkeypatch):
    original=stats.network_snapshot
    def reset_during_read(key,days):
        result=original(key,days)
        store.reset()
        return result
    monkeypatch.setattr(stats,'network_snapshot',reset_during_read)
    app=Flask(__name__);register_optimizer_routes(app)
    response=app.test_client().get('/api/repeater-optimizer?public_key='+KEY,headers=HEADERS)
    assert response.status_code==409
    assert 'Retry loading' in response.json['error']
