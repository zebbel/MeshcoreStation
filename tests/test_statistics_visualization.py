"""Saved-only aggregation, directional evidence, gaps and scope attribution."""
import hashlib
import hmac
import json
import sqlite3
from contextlib import closing
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from flask import Flask
from meshcorestation import config
from meshcorestation.storage import database,voltage_store,passive_stats as store
from meshcorestation.storage.statistics_view import aggregate,save_regions,scope_resolver

A='aa11'+'01'*30
B='bb22'+'02'*30
C='cc33'+'03'*30
D='dd44'+'04'*30
NOW=1800000000.0

@pytest.fixture
def station(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_FILE',tmp_path/'meshcorestation.db')
    monkeypatch.setattr(config,'DB_PATH',database.DB_FILE)
    owner=database.Database(Mock())
    for key,name,lat,lon in [(A,'Selected',49.6,8.6),(B,'Unmanaged neighbor',49.7,8.7),(C,'No coordinates',None,None),(D,'Only incoming',49.5,8.5)]:
        owner.add_new_repeater(NS(payload=dict(type=2,public_key=key,adv_name=name,adv_lat=lat,adv_lon=lon)),observed=False)
    with owner.db:
        voltage_store.ensure_repeater(owner.db,A)
        owner.db.execute('UPDATE voltage_config SET statistics_since_ns=0 WHERE public_key=?',(A,))
    yield owner
    owner.close()


def add(path='aa11bb22',kind=5,route=1,payload=b'packet',at=NOW-100,transport=None,size=2):
    rx=dict(path=path,path_hash_size=size,path_len=len(path)//(2*size),payload_type=kind,route_type=route,pkt_payload=payload,transport_code=transport)
    p=store.normalize(rx,now_ns=int(at*1e9));assert p
    return store.store_batch(database.DB_FILE,[p])


def test_neighbor_directions_unmanaged_positions_and_ambiguous_separation(station):
    add();add() # two distinct receptions, same packet digest
    add('bb22aa11',payload=b'reverse');add('aa11cc33',payload=b'no-coords')
    add('dd44aa11',payload=b'incoming')
    add('aa11bb22',route=2,payload=b'direct-instruction')
    add('aa11bb22',kind=9,payload=b'trace')
    # An unmanaged registry collision must block confirmed neighbor identity.
    station.add_new_repeater(NS(payload=dict(type=2,public_key='bb99'+'05'*30,adv_name='Collision')),observed=False)
    add('aabb',size=1,payload=b'ambiguous-neighbor')
    view=aggregate(database.DB_FILE,A,1,now=NOW)
    neighbors={n['public_key']:n for n in view['neighbors']}
    assert neighbors[B]['outgoing']==2 and neighbors[B]['incoming']==1
    assert neighbors[B]['outgoing_unique']==1
    assert neighbors[B]['name']=='Unmanaged neighbor'
    assert neighbors[C]['latitude'] is None and neighbors[C]['incoming']==0
    assert neighbors[D]['incoming']==1 and neighbors[D]['outgoing']==0
    assert view['ambiguous'] and any(n['candidates']==[B,'bb99'+'05'*30] for n in view['ambiguous'])
    assert not store.statistics_path(database.DB_FILE,B).exists()
    assert view['excluded']==2 # direct route + TRACE, not the unambiguous target in ambiguous edge


def test_current_registry_collision_never_upgrades_saved_confirmed_identity(station):
    add()
    station.add_new_repeater(NS(payload=dict(type=2,public_key='aa11'+'99'*30)),observed=False)
    view=aggregate(database.DB_FILE,A,1,now=NOW)
    assert view['totals']['receptions']==0 and not view['neighbors'] and view['ambiguous']


def test_hourly_text_types_unique_repeats_hop_rank_and_period_filters(station):
    add(payload=b'group');add(payload=b'group');add(kind=2,payload=b'private-text')
    add(kind=6,payload=b'not-text',path='bb22aa11cc33')
    add(payload=b'older',at=NOW-2*86400)
    add(kind=2,route=2,payload=b'not-observed-forwarding')
    view=aggregate(database.DB_FILE,A,1,now=NOW)
    hour=next(h for h in view['hourly'] if h['receptions'])
    assert hour['receptions']==3 and hour['unique_packets']==2 and hour['repeated']==1
    assert not hour['complete']
    assert any(h['receptions'] is None for h in view['hourly'])
    assert view['hops'][0]['hop_count']==2 and view['hops'][0]['receptions']==3
    assert view['hops'][1]['hop_count']==3 and view['hops'][1]['receptions']==1
    assert view['totals']['receptions']==4
    assert aggregate(database.DB_FILE,A,7,now=NOW)['totals']['receptions']==5
    assert aggregate(database.DB_FILE,A,30,now=NOW)['totals']['receptions']==5
    with pytest.raises(ValueError):aggregate(database.DB_FILE,A,3,now=NOW)
    with pytest.raises(ValueError):aggregate(database.DB_FILE,B,1,now=NOW)


def code(name,payload,kind=5):
    key=hashlib.sha256(('#'+name).encode()).digest()[:16]
    v=int.from_bytes(hmac.new(key,bytes([kind])+payload,hashlib.sha256).digest()[:2],'little')
    v=1 if v==0 else 65534 if v==65535 else v
    return v.to_bytes(2,'little').hex()+'1234'


def test_regions_transport_verification_unknown_unscoped_percentages_and_config(station):
    save_regions(database.DB_FILE,[dict(name='de-he'),dict(name='rhein-neckar')])
    with station.db:station.db.execute('INSERT INTO scopes VALUES(?,?)',('de-bw',hashlib.sha256(b'#de-bw').digest()[:16].hex()))
    for _ in range(3):add(payload=b'unscoped')
    for _ in range(2):add(route=0,payload=b'he',transport=code('de-he',b'he'))
    add(kind=2,route=0,payload=b'private',transport=code('de-bw',b'private',2))
    add(route=0,payload=b'unknown',transport=code('unconfigured',b'unknown'))
    add(route=0,payload=b'no-code')
    add(route=0,payload=b'wildcard',transport='00000000')
    view=aggregate(database.DB_FILE,A,1,now=NOW)
    regions={r['name']:r for r in view['regions']}
    assert view['regions'][0]['name']=='Unscoped'
    assert regions['Unscoped']['receptions']==4 and regions['Unscoped']['repeated']==2
    assert regions['de-he']['receptions']==2 and regions['de-he']['unique_packets']==1
    assert regions['Unknown']['receptions']==2 and regions['de-bw']['receptions']==1
    assert sum(r['percentage'] for r in view['regions'])==pytest.approx(100)
    assert 'scope_key' not in json.dumps(view)
    # Aliased keys and 16-bit transport-code collisions cannot choose a name.
    alias=hashlib.sha256(b'#de-he').digest()[:16].hex()
    resolve=scope_resolver([dict(name='a',scope_key=alias),dict(name='b',scope_key=alias)])
    assert resolve(5,b'he',code('de-he',b'he'),0)=='Unknown'
    for bad in [[dict(name='Unscoped')],[dict(name='bad name')],[dict(name='ok',scope_key='zz')]]:
        with pytest.raises(ValueError):save_regions(database.DB_FILE,bad)


def test_scope_resolver_reserved_codes_and_payload_type(monkeypatch):
    class Digest:
        def digest(self):return b'\x00\x00'+bytes(30)
    monkeypatch.setattr(hmac,'new',lambda *a:Digest())
    resolve=scope_resolver([dict(name='region',scope_key='11'*16)])
    assert resolve(2,b'payload','01000000',0)=='region'
    assert resolve(2,None,'01000000',0)=='Unknown'
    assert resolve(2,b'payload','bad',0)=='Unknown'


def test_coverage_preserves_legacy_unknown_gaps_and_does_not_create_files(station):
    store.record_coverage(database.DB_FILE,NOW-3600,NOW)
    assert not store.statistics_path(database.DB_FILE,A).exists()
    add()
    empty=aggregate(database.DB_FILE,A,1,now=NOW)
    assert empty['coverage_seconds']==0 and not empty['coverage_known']
    # Two healthy intervals separated by a disconnect; never bridge the gap.
    store.record_coverage(database.DB_FILE,NOW-7200,NOW-3600)
    store.record_coverage(database.DB_FILE,NOW-1800,NOW-10)
    view=aggregate(database.DB_FILE,A,1,now=NOW)
    assert view['coverage_seconds']==pytest.approx(5390)
    assert any(h['receptions']==0 and h['complete'] for h in view['hourly'])
    assert any(h['receptions'] is None for h in view['hourly'])
    with station.db:station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(A,))
    path=store.statistics_path(database.DB_FILE,A)
    with sqlite3.connect(path) as db:before=db.execute('SELECT MAX(ended_at) FROM collection_windows').fetchone()[0]
    store.record_coverage(database.DB_FILE,NOW,NOW+10)
    with sqlite3.connect(path) as db:assert db.execute('SELECT MAX(ended_at) FROM collection_windows').fetchone()[0]==before


def test_read_only_view_api_regions_guard_and_persistence(station):
    from meshcorestation.web.statistics_api import register_statistics_routes
    app=Flask(__name__);register_statistics_routes(app);client=app.test_client()
    response=client.get('/api/repeater-statistics/view?public_key='+A+'&days=1')
    assert response.status_code==200 and response.json['hourly']
    assert not store.statistics_path(database.DB_FILE,A).exists()
    assert client.get('/api/repeater-statistics/view?days=2').status_code==400
    assert client.get('/api/repeater-statistics/view?public_key='+B).status_code==400
    assert client.post('/api/repeater-statistics/regions',json={'regions':[]}).status_code==403
    headers={'X-Meshcore-Control':'1'}
    assert client.post('/api/repeater-statistics/regions',headers=headers,json={'regions':[{'name':'de-he'}]}).status_code==200
    assert client.get('/api/repeater-statistics/regions',headers=headers).json['regions'][0]['name']=='de-he'
    assert client.post('/api/repeater-statistics/regions',headers={**headers,'Origin':'https://evil.example'},json={'regions':[]}).status_code==403
    assert client.post('/api/repeater-statistics/regions',headers=headers,json={'regions':[{'name':'Unknown'}]}).status_code==400


def test_coverage_collector_disconnect_loss_and_recovery_do_not_bridge_gaps(station,monkeypatch):
    import asyncio
    from meshcorestation.radio import statistics_collector as module
    add()
    clock=[NOW,100.0]
    monkeypatch.setattr(module,'time',NS(time=lambda:clock[0],monotonic=lambda:clock[1]))
    async def run():
        collector=module.Collector(database.DB_FILE,Mock())
        collector.connected=True
        await collector.coverage()
        clock[0]+=5;clock[1]+=5;await collector.coverage()
        collector.connected=False
        clock[0]+=10;clock[1]+=10;await collector.coverage()
        collector.connected=True;await collector.coverage()
        clock[0]+=5;clock[1]+=5;await collector.coverage()
        collector.dropped+=1
        clock[0]+=5;clock[1]+=5;await collector.coverage()
        clock[0]+=5;clock[1]+=5;await collector.coverage()
    asyncio.run(run())
    path=store.statistics_path(database.DB_FILE,A)
    with sqlite3.connect(path) as db:
        windows=db.execute('SELECT started_at,ended_at FROM collection_windows ORDER BY started_at').fetchall()
    assert windows==[(NOW,NOW+5),(NOW+15,NOW+20),(NOW+25,NOW+30)]


def test_missing_payload_is_unidentified_not_a_unique_or_repeated_packet(station):
    add(payload=None)
    view=aggregate(database.DB_FILE,A,1,now=NOW)
    row=next(h for h in view['hourly'] if h['receptions'])
    assert row['unidentified']==1 and row['unique_packets']==row['repeated']==0
    empty=next(h for h in view['hourly'] if h['receptions'] is None)
    assert empty['unidentified'] is None
