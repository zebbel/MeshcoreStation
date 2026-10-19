"""Multi-repeater persistence, scheduling and passive collection regressions."""
import asyncio
import logging
import sqlite3
import time
from types import SimpleNamespace

import pytest
from flask import Flask, request
from meshcorestation.storage import voltage_store as store, passive_stats as stats
from meshcorestation.storage import database
from meshcorestation.web import voltage_api
from meshcorestation.radio.voltage_monitor import VoltageMonitor

A, B = 'aa'*32, 'bb'*32


@pytest.fixture
def station(tmp_path, monkeypatch):
    path = tmp_path / 'station.db'
    monkeypatch.setattr(database, 'DB_FILE', path)
    monkeypatch.setattr(voltage_api, 'DB_PATH', path)
    monkeypatch.setattr(voltage_api, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(stats, 'DB_PATH', path)
    monkeypatch.setattr(stats, 'STATS_PATH', tmp_path / 'stats.db')
    owner = database.Database(logging.getLogger('test'))
    db = owner.db
    store.initialize(db)
    with db:
        for key, name in ((A,'Hill'),(B,'City')):
            db.execute('INSERT INTO repeaters(public_key,name,adv_type,first_seen,last_seen) VALUES (?,?,2,0,0)', (key,name))
    stats.initialize()
    app = Flask(__name__)
    app.add_url_rule('/voltage', view_func=lambda: voltage_api.voltage_request(request), methods=['GET','POST'])
    yield db, app.test_client()
    owner.close()


def test_migrate_legacy_settings_and_report_reservations():
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
    # Recreate the old singleton schema from the current table definition.
    store.initialize(db)
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name='voltage_config'").fetchone()[0]
    db.execute('DROP TABLE voltage_config')
    db.execute(sql.replace('id INTEGER PRIMARY KEY', 'id INTEGER PRIMARY KEY CHECK(id=1)'))
    db.execute('INSERT INTO voltage_config(id,public_key,enabled,revision,request_seq) VALUES(1,?,1,7,3)', (A,))
    db.execute("INSERT INTO voltage_reports VALUES ('Europe/Berlin|2026-10-19|08:00',?,0,0,NULL,'queued','sent')", (A,))
    store.initialize(db); store.initialize(db)
    cfg = store.config(db,A)
    assert (cfg['enabled'],cfg['revision'],cfg['request_seq']) == (True,7,3)
    db.execute('INSERT INTO voltage_config(public_key) VALUES (?)', (B,))
    assert len(store.configurations(db)) == 2
    assert db.execute('SELECT slot FROM voltage_reports').fetchone()[0] == A+'|Europe/Berlin|2026-10-19|08:00'
    db.close()


def test_api_independent_settings_revisions_and_manual_reads(station):
    db, client = station
    for key in (A,B):
        assert client.post('/voltage',json={'operation':'add','public_key':key}).status_code == 200
    for key, interval, channel in ((A,5,1),(B,60,2)):
        cfg = client.get('/voltage?public_key='+key).json['config']
        value = {field:cfg[field] for field in store.FIELDS}
        value.update(enabled=True, interval_minutes=interval, voltage_channel=channel)
        assert client.post('/voltage?public_key='+key, json={'operation':'save','value':value,'expected_revision':0}).status_code == 200
        assert client.post('/voltage?public_key='+key, json={'operation':'save','value':value,'expected_revision':0}).status_code == 409
    assert store.config(db,A)['interval_minutes'] == 5
    assert store.config(db,B)['interval_minutes'] == 60
    assert store.config(db,A)['revision'] == store.config(db,B)['revision'] == 1
    with db:
        db.execute("INSERT OR REPLACE INTO voltage_worker VALUES (1,?,'idle')", (time.time(),))
    assert client.post('/voltage?public_key='+B,json={'operation':'sample','expected_revision':1}).status_code == 200
    assert store.config(db,A)['request_seq'] == 0
    assert store.config(db,B)['request_seq'] == 1
    assert set(client.get('/voltage').json['managed_repeaters']) == {A,B}
    with stats.connect() as stats_db:
        assert {r['public_key'] for r in stats.collection_targets(stats_db)} == {A,B}


def sample_row(db,key,stamp,voltage=3.9,error=None):
    db.execute('''INSERT INTO voltage_samples(public_key,name,sampled_at,voltage,error,voltage_channel,interval_seconds)
                  VALUES (?, ?, ?, ?, ?, 1, 1800)''',(key,key[:4],stamp,voltage,error))


def monitor(db):
    return VoltageMonitor(SimpleNamespace(database=SimpleNamespace(db=db),logger=logging.getLogger('test')))


def test_same_time_reports_are_independent_and_not_retried(station,monkeypatch):
    db, _ = station
    with db:
        for key in (A,B):
            store.ensure_repeater(db,key)
            db.execute('UPDATE voltage_config SET enabled=1 WHERE public_key=?',(key,))
            sample_row(db,key,time.time()-300)
    m = monitor(db); sent=[]
    async def report(slot,cfg,sample): sent.append((slot,cfg['public_key'],sample['voltage']))
    async def forbidden(cfg): pytest.fail('Report attempted a new telemetry read')
    m.report=report; m.sample=forbidden
    monkeypatch.setattr('meshcorestation.radio.voltage_monitor.due_slots',lambda cfg,now:[('same-time',now)])
    asyncio.run(m.tick()); asyncio.run(m.tick())
    assert sent == [(A+'|same-time',A,3.9),(B+'|same-time',B,3.9)]
    assert db.execute('SELECT COUNT(*) FROM voltage_reports').fetchone()[0] == 2


def test_failed_repeater_does_not_starve_another(station,monkeypatch):
    db, _ = station
    with db:
        for key in (A,B):
            store.ensure_repeater(db,key)
            db.execute('UPDATE voltage_config SET enabled=1,reports_enabled=0 WHERE public_key=?',(key,))
    m=monitor(db); reads=[]
    async def sample(cfg):
        reads.append(cfg['public_key'])
        with db: sample_row(db,cfg['public_key'],time.time(),None,'Timeout')
    m.sample=sample
    asyncio.run(m.tick()); assert reads == [A]
    asyncio.run(m.tick()); assert reads == [A,B]
    asyncio.run(m.tick()); assert reads == [A,B]


def test_passive_packet_collected_for_both_and_pause_is_local(station):
    _, client = station
    for key in (A,B): client.post('/voltage',json={'operation':'add','public_key':key})
    packet=stats.normalize({'route_type':1,'payload_type':5,'path_len':2,'path_hash_size':1,'path':'aabb','pkt_payload':b'ciphertext'})
    with stats.connect() as db:
        stats.store_batch(db,[(time.time(),packet)],stats.known_repeaters())
    assert stats.snapshot(1,A)['copies'] == stats.snapshot(1,B)['copies'] == 1
    stats.track(A,False)
    with stats.connect() as db:
        stats.store_batch(db,[(time.time(),packet)],stats.known_repeaters())
    assert stats.snapshot(1,A)['copies'] == 1
    assert stats.snapshot(1,B)['copies'] == 2
    assert not stats.snapshot(1,A)['collection_enabled']
    assert stats.snapshot(1,B)['collection_enabled']


def test_paused_legacy_target_stays_in_managed_list(station):
    _, client = station
    stats.select(A)
    stats.track(A,False)
    assert A in client.get('/voltage').json['managed_repeaters']
    assert not stats.snapshot(1,A)['collection_enabled']


def test_history_and_report_logs_are_scoped_to_repeater(station):
    db, client = station
    with db:
        for key in (A,B):
            store.ensure_repeater(db,key)
            sample_row(db,key,time.time(),3.5 if key == A else 4.1)
            db.execute("INSERT INTO voltage_reports VALUES (?,?,0,0,NULL,'queued',?)", (key+'|morning',key,key))
    for key, voltage in ((A,3.5),(B,4.1)):
        data=client.get('/voltage?public_key='+key).json
        assert data['latest']['voltage'] == voltage
        assert len(data['samples']) == 1
        assert [r['public_key'] for r in data['reports']] == [key]


def test_remove_deletes_target_data_only_and_readd_starts_clean(station):
    db, client = station
    for key in (A,B):
        client.post('/voltage',json={'operation':'add','public_key':key})
    with db:
        for key in (A,B):
            sample_row(db,key,time.time())
            db.execute("INSERT INTO voltage_reports VALUES (?,?,0,0,NULL,'queued','sent')", (key+'|morning',key))
        db.execute("UPDATE voltage_config SET enabled=1,interval_minutes=90,report_target='channel:Private' WHERE public_key=?", (A,))
    packet=stats.normalize({'route_type':1,'payload_type':5,'path_len':2,'path_hash_size':1,'path':'aabb','pkt_payload':b'ciphertext'})
    with stats.connect() as connection:
        stats.store_batch(connection,[(time.time(),packet)],stats.known_repeaters())
    old_revision=store.config(db,A)['revision']
    assert client.post('/voltage',json={'operation':'remove','public_key':A}).status_code == 200
    assert client.get('/voltage').json['managed_repeaters'] == [B]
    assert not db.execute('SELECT 1 FROM voltage_samples WHERE public_key=?',(A,)).fetchone()
    assert not db.execute('SELECT 1 FROM voltage_reports WHERE public_key=?',(A,)).fetchone()
    assert stats.snapshot(1,A)['copies'] == 0
    assert stats.snapshot(1,B)['copies'] == 1
    assert db.execute('SELECT COUNT(*) FROM voltage_samples WHERE public_key=?',(B,)).fetchone()[0] == 1
    assert store.config(db,A)['revision'] > old_revision
    assert client.post('/voltage?public_key='+A,json={'operation':'sample','expected_revision':store.config(db,A)['revision']}).status_code == 400
    client.post('/voltage',json={'operation':'add','public_key':A})
    cfg=store.config(db,A)
    assert cfg['interval_minutes'] == 30 and cfg['report_target'] == 'bot' and not cfg['enabled']
    assert client.get('/voltage?public_key='+A).json['samples'] == []
    for key in (A,B): client.post('/voltage',json={'operation':'remove','public_key':key})
    assert client.get('/voltage').json['managed_repeaters'] == []
    assert store.configurations(db) == []


def test_in_flight_read_cannot_recreate_removed_data(station):
    from meshcore import EventType
    db, client = station
    client.post('/voltage',json={'operation':'add','public_key':A})
    cfg=store.config(db,A)
    class Commands:
        async def get_contacts(self):
            client.post('/voltage',json={'operation':'remove','public_key':A})
            return SimpleNamespace(type=EventType.CONTACTS,payload={A:{'public_key':A,'type':2}})
        async def send_login_sync(self,*args,**kwargs):
            return SimpleNamespace(type=EventType.LOGIN_SUCCESS,payload={'pubkey_prefix':A[:12]})
        async def req_telemetry_sync(self,*args,**kwargs):
            return [{'type':'voltage','channel':1,'value':4.0}]
    m=monitor(db)
    m.companion.mc=SimpleNamespace(commands=Commands())
    assert asyncio.run(m.sample(cfg)) is None
    assert db.execute('SELECT COUNT(*) FROM voltage_samples').fetchone()[0] == 0
