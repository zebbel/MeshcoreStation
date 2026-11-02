"""Managed-only passive collection, queue boundaries and persistent evidence."""
import asyncio
from contextlib import closing
import json
import logging
import sqlite3
import threading
import time
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from flask import Flask
from meshcorestation import config
from meshcorestation.storage import database, passive_stats as stats, voltage_store
from meshcorestation.radio.statistics_collector import Collector

A='aa11'+'01'*30
B='bb22'+'02'*30
COLLISION='aa33'+'03'*30
UNMANAGED='cc44'+'04'*30


@pytest.fixture
def station(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_FILE',tmp_path/'meshcorestation.db')
    monkeypatch.setattr(config,'DB_PATH',database.DB_FILE)
    owner=database.Database(logging.getLogger('statistics-test'))
    for key,name in [(A,'Alpha'),(B,'Beta'),(COLLISION,'Collision'),(UNMANAGED,'Unmanaged')]:
        owner.add_new_repeater(NS(payload=dict(type=2,public_key=key,adv_name=name)),observed=False)
    yield owner
    owner.close()


def manage(station,*keys):
    with voltage_store.MEMBERSHIP_LOCK,station.db:
        for key in keys:voltage_store.ensure_repeater(station.db,key)


def packet(path='aa11bb22cc44',size=2,kind=6,route=0,**extra):
    return dict(payload_type=kind,route_type=route,path_hash_size=size,path_len=len(path)//(size*2),
                path=path,pkt_payload=b'original bytes',rssi=-98,snr=2.25,transport_code='12345678',**extra)


def records(key):
    path=stats.statistics_path(database.DB_FILE,key)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory=sqlite3.Row
        return [dict(row) for row in db.execute('SELECT * FROM observations ORDER BY id')]


def write(*rx):
    return stats.store_batch(database.DB_FILE,[stats.normalize(p) for p in rx])


def test_no_files_until_relevant_managed_observation_and_multiple_targets(station):
    manage(station,A,B)
    assert not stats.statistics_path(database.DB_FILE,A).parent.exists()
    # This is only an unmanaged route: no file or directory may be created.
    assert write(packet(path='cc44'))==({}, {})
    assert not stats.statistics_path(database.DB_FILE,A).parent.exists()
    saved,errors=write(packet())
    assert saved=={A:1,B:1} and not errors
    assert not stats.statistics_path(database.DB_FILE,UNMANAGED).exists()
    first,second=records(A)[0],records(B)[0]
    assert first['reception_id']==second['reception_id']
    assert first['first_hop']==1 and second['middle_hop']==1
    assert json.loads(first['following'])[0]['public_key']==B
    assert json.loads(second['previous'])[0]['public_key']==A
    assert first['payload']==b'original bytes' and first['rssi']==-98 and first['snr']==2.25
    assert first['scoped']==1 and first['transport_code']=='12345678'
    path=stats.statistics_path(database.DB_FILE,A)
    assert path.stat().st_mode&0o077==0
    assert path.parent.stat().st_mode&0o077==0
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert 'observations_timestamp' in {r[1] for r in db.execute('PRAGMA index_list(observations)')}


def test_collisions_include_unmanaged_registry_and_repeated_receptions_are_not_deduplicated(station):
    manage(station,A)
    original=packet(path='aabb',size=1)
    write(original,original)
    rows=records(A)
    assert len(rows)==2 and rows[0]['packet_digest']==rows[1]['packet_digest']
    assert rows[0]['reception_id']!=rows[1]['reception_id']
    assert all(r['ambiguous']==1 and r['first_hop']==0 for r in rows)
    hop=json.loads(rows[0]['route'])[0]
    assert hop['public_key'] is None and set(hop['candidates'])=={A,COLLISION}
    assert not stats.statistics_path(database.DB_FILE,COLLISION).exists()
    # Wider hashes unambiguously resolve to the complete key.
    write(packet(path='aa11'))
    assert records(A)[-1]['confidence']=='unambiguous-hash'
    assert records(A)[-1]['ambiguous']==0


def test_remove_drops_queued_packets_and_readd_preserves_history(station):
    manage(station,A)
    write(packet(path='aa11'))
    stale=stats.normalize(packet(path='aa11'))
    with voltage_store.MEMBERSHIP_LOCK,station.db:
        station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(A,))
    assert stats.store_batch(database.DB_FILE,[stale])==({}, {})
    assert len(records(A))==1
    unmanaged_packet=stats.normalize(packet(path='aa11'))
    manage(station,A)
    assert stats.store_batch(database.DB_FILE,[stale,unmanaged_packet])==({}, {})
    write(packet(path='aa11'))
    assert len(records(A))==2
    assert stats.snapshot(database.DB_FILE,A)['observation_count']==2


def test_membership_removal_serializes_with_inflight_batch(station,monkeypatch):
    manage(station,A)
    entered=threading.Event();release=threading.Event();removed=threading.Event()
    original=stats._write
    def slow(*args):
        entered.set();assert release.wait(3);original(*args)
    monkeypatch.setattr(stats,'_write',slow)
    observation=stats.normalize(packet(path='aa11'))
    writer=threading.Thread(target=lambda:stats.store_batch(database.DB_FILE,[observation]))
    writer.start();assert entered.wait(3)
    def remove():
        with voltage_store.MEMBERSHIP_LOCK,sqlite3.connect(database.DB_FILE) as db:
            db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(A,))
        removed.set()
    remover=threading.Thread(target=remove);remover.start()
    assert not removed.wait(.03)
    release.set();writer.join(3);remover.join(3);assert removed.is_set()
    assert stats.store_batch(database.DB_FILE,[observation])==({}, {})
    assert len(records(A))==1


@pytest.mark.parametrize('kind',range(16))
def test_all_client_packet_types_are_passive_and_bot_channel_independent(station,kind):
    manage(station,A)
    async def run():
        from meshcorestation.radio.companion import Companion
        c=Companion(Mock(),station)
        # No connected MC, tracking key or Bot-channel binding is needed.
        collector=Collector(database.DB_FILE,Mock(),interval=.001)
        collector.start();c.statistics=collector
        try:
            c._handle_rx_log(NS(payload=packet(path='aa11',kind=kind,chan_hash='99')))
            await asyncio.wait_for(collector.queue.join(),2)
        finally:await collector.close()
    asyncio.run(run())
    row=records(A)[0]
    assert row['packet_type']==kind
    if kind==9:assert row['ambiguous']==1 and not json.loads(row['positions'])


@pytest.mark.parametrize('route',[0,1,2,3])
def test_route_types_preserve_raw_evidence_without_direct_forwarding_claims(station,route):
    manage(station,A)
    write(packet(path='aa11',route=route))
    row=records(A)[0]
    assert row['route_type']==route and row['scoped']==int(route in (0,3))
    if route in (2,3):
        assert row['confidence']=='ambiguous' and row['first_hop']==row['last_hop']==0
        assert row['evidence']=='direct-routing-path' and json.loads(row['positions'])==[]


def test_advert_origin_without_hops_and_metadata_bytes_timestamps_preserved(station):
    manage(station,A)
    rx=packet(path='',kind=4,sender_timestamp=1234,channel_secret=b'never save')
    rx['pkt_payload']=bytes.fromhex(A)+b'\0'*68+b'\x02'
    p=stats.normalize(rx)
    stats.store_batch(database.DB_FILE,[p])
    row=records(A)[0]
    assert row['evidence']=='advertisement-origin' and row['first_hop']==0
    assert row['received_at']==p['received_at']
    metadata=json.loads(row['metadata'])
    assert metadata['sender_timestamp']==1234 and 'channel_secret' not in metadata
    assert metadata['pkt_payload']['hex']==rx['pkt_payload'].hex()


def test_missing_malformed_fields_and_four_byte_hashes(station):
    manage(station,A)
    for rx in [{},packet(path='a'),{**packet(),'path_len':True},{**packet(),'path_hash_size':5},
               {**packet(),'pkt_payload':'zz'},{**packet(),'route_type':-1}]:
        assert stats.normalize(rx) is None
    write(packet(path=A[:8],size=4))
    assert records(A)[0]['path_hash_size']==4
    with pytest.raises(ValueError):stats.statistics_path(database.DB_FILE,'../escape')


def test_low_disk_and_database_failure_preserve_data_and_resume(station,monkeypatch):
    manage(station,A,B)
    write(packet(path='aa11'))
    original=stats.shutil.disk_usage
    monkeypatch.setattr(stats.shutil,'disk_usage',lambda _:NS(free=1))
    saved,errors=write(packet())
    assert not saved and set(errors)=={A,B} and '64 MiB' in errors[A]['error']
    assert len(records(A))==1 and not stats.statistics_path(database.DB_FILE,B).exists()
    monkeypatch.setattr(stats.shutil,'disk_usage',original)
    writer=stats._write
    def fail_one(path,rows):
        if path.stem==A:raise sqlite3.OperationalError('database is locked')
        writer(path,rows)
    monkeypatch.setattr(stats,'_write',fail_one)
    saved,errors=write(packet())
    assert saved=={B:1} and A in errors and len(records(A))==1
    monkeypatch.setattr(stats,'_write',writer)
    assert write(packet())[0]=={A:1,B:1}


def test_queue_overflow_nonblocking_writes_errors_shutdown_and_restart(station,monkeypatch):
    manage(station,A)
    original=stats.store_batch
    entered=threading.Event();release=threading.Event()
    def slow(*args):
        entered.set();assert release.wait(3);return original(*args)
    monkeypatch.setattr(stats,'store_batch',slow)
    async def run():
        collector=Collector(database.DB_FILE,Mock(),capacity=1,interval=.001)
        collector.start();collector.submit(packet(path='aa11'));collector.submit(packet(path='aa11'))
        assert collector.dropped==1
        for _ in range(100):
            if entered.is_set():break
            await asyncio.sleep(.005)
        assert entered.is_set()
        # Event loop still responds while the SQLite worker is blocked.
        await asyncio.wait_for(asyncio.sleep(.001),.05)
        release.set();await collector.queue.join()
        def broken(*args):raise sqlite3.OperationalError('temporarily unavailable')
        monkeypatch.setattr(stats,'store_batch',broken)
        collector.submit(packet(path='aa11'));await collector.queue.join()
        assert 'temporarily unavailable' in collector.error
        monkeypatch.setattr(stats,'store_batch',original)
        collector.submit(packet(path='aa11'));await collector.close()
        assert not collector.health()['running'] and collector.error==''
        restarted=Collector(database.DB_FILE,Mock(),interval=.001)
        restarted.start();restarted.submit(packet(path='aa11'));await restarted.close()
    asyncio.run(run())
    assert len(records(A))==3


def test_status_managed_only_no_database_creation_offline_and_error_state(station,monkeypatch):
    from meshcorestation.web.statistics_api import register_statistics_routes
    from meshcorestation.bridge import bridge
    manage(station,A,B)
    app=Flask(__name__);register_statistics_routes(app);client=app.test_client()
    monkeypatch.setattr(bridge,'runtime',None)
    value=client.get('/api/repeater-statistics/status').json
    assert {r['public_key'] for r in value['repeaters']}=={A,B}
    assert value['health']['running'] is False and value['observation_count']==0
    assert not stats.statistics_path(database.DB_FILE,A).exists()
    assert client.get('/api/repeater-statistics/status?public_key='+UNMANAGED).status_code==400
    assert client.get('/api/repeater-statistics/status?public_key=../oops').status_code==400
    write(packet(path='aa11'))
    assert client.get('/api/repeater-statistics/status?public_key='+A).json['observation_count']==1
    path=stats.statistics_path(database.DB_FILE,B);path.write_bytes(b'broken database')
    value=client.get('/api/repeater-statistics/status?public_key='+B).json
    assert value['observation_count'] is None and value['error']


def test_existing_v5_membership_gets_additive_cutoff_without_data_loss(station):
    manage(station,A)
    station.db.execute("INSERT INTO logger(message,recv_time) VALUES('preserved',123)")
    station.db.commit()
    # Reproduce the published V5 table shape before this feature's additive column.
    station.db.execute('ALTER TABLE voltage_config DROP COLUMN statistics_since_ns')
    station.db.commit()
    voltage_store.initialize(station.db)
    cfg=voltage_store.config(station.db,A)
    assert cfg['managed']==1 and cfg['enabled'] is False and cfg['statistics_since_ns']==0
    assert station.db.execute('SELECT message FROM logger').fetchone()[0]=='preserved'
    write(packet(path='aa11'))
    assert len(records(A))==1


def test_api_management_removal_preserves_statistics_and_invalidates_queue(station,monkeypatch):
    from flask import request
    from meshcorestation.web import voltage_api
    monkeypatch.setattr(voltage_api,'DB_PATH',database.DB_FILE)
    app=Flask(__name__)
    @app.post('/management')
    def management():return voltage_api.voltage_request(request)
    client=app.test_client()
    assert client.post('/management',json={'operation':'add','public_key':A}).status_code==200
    write(packet(path='aa11'))
    queued=stats.normalize(packet(path='aa11'))
    assert client.post('/management',json={'operation':'remove','public_key':A}).status_code==200
    assert stats.store_batch(database.DB_FILE,[queued])==({}, {})
    assert len(records(A))==1 and not stats.snapshot(database.DB_FILE)['repeaters']
    assert client.post('/management',json={'operation':'add','public_key':A}).status_code==200
    assert stats.store_batch(database.DB_FILE,[queued])==({}, {})
    write(packet(path='aa11'))
    assert len(records(A))==2
