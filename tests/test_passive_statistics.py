import asyncio
import json
import sqlite3
import time
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from flask import Flask
from meshcorestation.storage import passive_stats as s
from meshcorestation.web.passive_api import register_passive_routes

TARGET='769b'+'00'*30
BEFORE='e59a'+'00'*30
AFTER='aaaa'+'00'*30

@pytest.fixture
def db(tmp_path,monkeypatch):
    main=tmp_path/'main.db'
    with sqlite3.connect(main) as connection:
        connection.execute('CREATE TABLE repeaters(public_key TEXT,name TEXT)')
        connection.executemany('INSERT INTO repeaters VALUES(?,?)',[(TARGET,'My repeater'),(BEFORE,'Before'),(AFTER,'After')])
    monkeypatch.setattr(s,'DB_PATH',main);monkeypatch.setattr(s,'STATS_PATH',tmp_path/'stats.db')
    s.initialize()
    return main


def packet(path='e59a769baaaa',**extra):
    return {'route_type':1,'payload_type':5,'path_len':len(path)//4,'path_hash_size':2,'path':path,'pkt_payload':b'encrypted data',**extra}


def insert(target,p,repeaters,at=None):
    values=s.attribute(p,target,repeaters)
    with s.connect() as connection:
        connection.execute('INSERT INTO observations(target,at,digest,kind,scoped,ambiguous,first_hop,middle_hop,last_hop,route,previous,following) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(target,at or time.time(),*values))


def test_selected_only_aggregate_repeated_and_neighbors(db):
    s.select(TARGET);p=s.normalize(packet());known=s.known_repeaters()
    insert(TARGET,p,known);insert(TARGET,p,known)
    insert(BEFORE,p,known) # another selection's retained history is not shown
    data=s.snapshot(1)
    assert (data['copies'],data['unique'],data['repeated'],data['ratio'])==(2,1,1,.5)
    assert data['roles']=={'First':0,'Middle':2,'Final':0}
    assert data['previous'][0]['name']=='Before' and data['following'][0]['name']=='After'
    assert sum(b['copies'] for b in data['timeline'])==2
    assert len(data['routes'])==1


def test_ambiguous_target_excluded_from_totals(db):
    known=s.known_repeaters()+[{'public_key':'769b'+'ff'*30,'name':'Collision'}]
    insert(TARGET,s.normalize(packet()),known)
    s.select(TARGET);data=s.snapshot(1)
    assert data['ambiguous']==1 and data['copies']==0
    assert data['previous']==[] and data['types']=={}


@pytest.mark.parametrize('extra',[{'route_type':2},{'route_type':3},{'payload_type':9},{'path_len':2},{'path_hash_size':4},{'path':'gg'}])
def test_invalid_or_direct_paths_excluded(extra):
    assert s.normalize(packet(**extra)) is None


@pytest.mark.parametrize('size',[1,2,3])
def test_hash_sizes_and_unknown_neighbors(db,size):
    prefix=TARGET[:size*2];raw='ff'*size+prefix
    p=s.normalize({'route_type':0,'payload_type':4,'path_hash_size':size,'path_len':2,'path':raw,'pkt_payload':b'advert'})
    values=s.attribute(p,TARGET,s.known_repeaters())
    assert values[2]==1 and values[6]==1
    assert json.loads(values[8])[0]['status']=='unknown'
    assert s.attribute(p,AFTER,s.known_repeaters()) is None


def test_missing_payload_does_not_fabricate_unique_counts(db):
    s.select(TARGET);insert(TARGET,s.normalize(packet(pkt_payload=None)),s.known_repeaters())
    data=s.snapshot(1)
    assert data['copies']==1 and data['unique']==0 and data['unidentified']==1 and data['ratio'] is None


def test_collector_background_storage_and_retention(db,monkeypatch):
    s.select(TARGET)
    insert(TARGET,s.normalize(packet()),s.known_repeaters(),time.time()-31*86400)
    worker=s.Collector();worker.start()
    try:
        worker.submit(packet())
        worker.submit(packet(path='e59aaaaa')) # no selected key
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            with s.connect() as connection:
                rows=connection.execute('SELECT * FROM observations').fetchall()
            if len(rows)==1 and rows[0]['at']>time.time()-10: break
            time.sleep(.02)
        assert len(rows)==1 and rows[0]['target']==TARGET and rows[0]['at']>time.time()-10
    finally: worker.close()
    assert not worker.thread.is_alive()


def test_selection_pause_and_api_guards(db):
    app=Flask(__name__);register_passive_routes(app);client=app.test_client();headers={'X-Meshcore-Control':'1'}
    assert client.get('/api/repeater-statistics').status_code==403
    assert client.post('/api/repeater-statistics',headers={**headers,'Origin':'https://evil.test'},json={'public_key':TARGET}).status_code==403
    assert client.post('/api/repeater-statistics',headers=headers,json={'public_key':'invalid'}).status_code==400
    assert client.post('/api/repeater-statistics',headers=headers,json={'public_key':TARGET}).json['selection']['public_key']==TARGET
    assert client.get('/api/repeater-statistics?days=2',headers=headers).status_code==400
    assert client.post('/api/repeater-statistics',headers=headers,json={'public_key':''}).json['selection']['public_key']==''


def test_rx_hook_observes_non_bot_channel_before_filter(monkeypatch):
    from meshcorestation.radio.companion import Companion
    fake=Mock();monkeypatch.setattr(s,'collector',fake)
    companion=Companion.__new__(Companion)
    rx=packet(payload_type=4)
    companion._handle_rx_log(NS(payload=rx))
    fake.submit.assert_called_once_with(rx)


def test_storage_cap_and_no_payload_persistence(db,monkeypatch):
    monkeypatch.setattr(s,'MAX_ROWS',2)
    s.select(TARGET)
    for i in range(4):insert(TARGET,s.normalize(packet(pkt_payload=b'private secret')),s.known_repeaters(),time.time()-10+i)
    worker=s.Collector();worker.start()
    try:
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            with s.connect() as connection:
                rows=connection.execute('SELECT * FROM observations').fetchall()
                health=connection.execute('SELECT * FROM health').fetchone()
            if len(rows)==2:break
            time.sleep(.02)
        assert len(rows)==2 and health['trimmed_at']
        assert 'private secret' not in str([dict(r) for r in rows])
    finally:worker.close()


def test_queue_is_bounded_and_drops_visible():
    worker=s.Collector();worker.thread=NS(is_alive=lambda:True)
    for i in range(worker.queue.maxsize+3):worker.submit(packet())
    assert worker.queue.qsize()==2048 and worker.dropped==3


def test_distinct_neighbors_with_same_name_remain_separate(db):
    s.select(TARGET)
    known=s.known_repeaters()
    for r in known:r['name']='Same name'
    insert(TARGET,s.normalize(packet(path='e59a769b')),known)
    insert(TARGET,s.normalize(packet(path='aaaa769b')),known)
    data=s.snapshot(1)
    assert len(data['previous'])==2
    assert {r['key'] for r in data['previous']}=={BEFORE,AFTER}
