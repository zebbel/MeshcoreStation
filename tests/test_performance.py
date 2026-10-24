"""Real captured analyzer bodies plus local packet/audit records. No remote/radio I/O."""
import copy
import json
import sqlite3
import time
from pathlib import Path
from flask import Flask
import pytest
from meshcorestation.storage import performance_store as p, passive_stats, optimizer_store, advisor_history
from meshcorestation.web.performance_api import register_performance_routes
from meshcorestation.analyzer import AnalyzerService

ROOT=Path(__file__).parent/'fixtures/analyzer'
KEY=json.loads((ROOT/'manifest.json').read_text())['repeater_public_key'];OTHER='cd'*32
FILES={'detail':'node_detail_24h.json','reach':'node_reach_1d.json','metrics':'graph_metrics.json'}
DATA={k:json.loads((ROOT/'responses'/f).read_text()) for k,f in FILES.items()}
NOW=2000000000.0

@pytest.fixture
def stores(tmp_path,monkeypatch):
    monkeypatch.setattr(p,'FILE',tmp_path/'repeater-performance.db')
    monkeypatch.setattr(passive_stats,'STATS_PATH',tmp_path/'statistics.db')
    monkeypatch.setattr(optimizer_store,'FILE',tmp_path/'optimizer.db')
    monkeypatch.setattr(advisor_history,'FILE',tmp_path/'audit.db')
    monkeypatch.setattr(passive_stats,'known_repeaters',lambda:[{'public_key':KEY,'name':'Selected'},{'public_key':OTHER,'name':'Other'}])
    passive_stats.initialize();optimizer_store.initialize()
    return tmp_path


def packet(at, key=KEY, digest='payload', tracked=False, ambiguous=0):
    from contextlib import closing
    with closing(passive_stats.connect()) as db,db:
        if tracked:
            route=json.dumps([{'key':key,'name':'Selected','status':'matched'}])
            db.execute('INSERT INTO observations(target,at,digest,kind,scoped,ambiguous,first_hop,middle_hop,last_hop,route,previous,following) VALUES(?,?,?,5,1,?,1,0,0,?,\'[]\',\'[]\')',(key,at,digest,ambiguous,route))
        else:
            db.execute('INSERT INTO network_observations(at,kind,scoped,path_len,hash_size,route,digest) VALUES(?,5,1,1,1,?,?)',(at,key[:2],digest))


def test_archive_deduplicates_cache_slots_and_never_adds_rolling_counts(stores):
    p.record_analyzer(KEY,NOW,DATA);p.record_analyzer(KEY,NOW,DATA)
    changed=copy.deepcopy(DATA);changed['detail']['stat']['relayCount1h']=9
    p.record_analyzer(KEY,NOW+1,changed)
    rows=p.measurements(KEY,NOW-1,NOW+5)
    assert len(rows)==1 and rows[0]['relay_1h']==9 and rows[0]['relay_24h']==107
    assert rows[0]['two_way']==4
    assert rows[0]['neighbors']==sum(n['role']=='Repeater' for n in DATA['reach']['neighbourList'])
    p.record_analyzer(KEY,NOW+901,DATA)
    assert len(p.measurements(KEY,NOW-1,NOW+1000))==2
    assert p.measurements(OTHER,NOW-1,NOW+1000)==[]
    result=p.overview(KEY,1,NOW+1000)
    assert sum(b['analyzer_at'] is not None for b in result['timeline'])<len(result['timeline'])
    assert any(b['relay_1h'] is None for b in result['timeline'])


def test_retention_caps_measurements_but_never_prunes_markers(stores,monkeypatch):
    ident=p.marker_change(KEY,'create',{'description':'Old antenna change','at':100},now=NOW)
    p.record_analyzer(KEY,NOW-p.RETENTION-1,DATA);p.record_analyzer(KEY,NOW,DATA)
    assert len(p.measurements(KEY,0,NOW+1))==1
    monkeypatch.setattr(p,'MAX_SAMPLES',2)
    for i in range(3):p.record_analyzer(KEY,NOW+(i+1)*901,DATA)
    assert len(p.measurements(KEY,0,NOW+10000))==2
    assert p.markers(KEY)[0]['id']==ident
    assert p.overview(KEY,1,NOW+p.RETENTION+10000)['analyzer'] is None
    assert p.markers(KEY)[0]['id']==ident


def test_marker_edit_delete_restart_identity_and_validation(stores):
    ident=p.marker_change(KEY,'create',{'description':'  Antenna replacement  ','at':NOW-1},now=NOW)
    assert p.markers(KEY)[0]['description']=='Antenna replacement'
    p.marker_change(KEY,'edit',{'id':ident,'description':'TX power adjustment','at':NOW-30},now=NOW)
    assert p.markers(KEY)[0]['at']==NOW-30
    with pytest.raises(ValueError):p.marker_change(OTHER,'delete',{'id':ident},now=NOW)
    for value in ['', 'a'*501, None]:
        with pytest.raises(ValueError):p.marker_change(KEY,'create',{'description':value},now=NOW)
    for at in [float('nan'),float('inf'),True,NOW+1000,-1,'today']:
        with pytest.raises(ValueError):p.marker_change(KEY,'create',{'description':'Change','at':at},now=NOW)
    p.marker_change(KEY,'delete',{'id':ident},now=NOW)
    assert p.markers(KEY)==[]
    with p.database() as db:assert db.execute('SELECT deleted FROM markers WHERE id=?',(ident,)).fetchone()[0]==1


def test_automatic_verified_markers_hook_backfill_and_tombstone(stores):
    ident=advisor_history.begin(KEY,'flood.max',10,8)
    advisor_history.finish(ident,'8','verified')
    rows=p.markers(KEY);assert len(rows)==1 and rows[0]['source_id']==str(ident)
    saved=rows[0];assert 'Verified flood.max' in saved['description']
    p.marker_change(KEY,'edit',{'id':saved['id'],'description':'My explanation','at':NOW-1},now=NOW)
    p.sync_verified(KEY);assert p.markers(KEY)[0]['description']=='My explanation'
    p.marker_change(KEY,'delete',{'id':saved['id']},now=NOW);p.sync_verified(KEY);assert not p.markers(KEY)
    bad=advisor_history.begin(KEY,'flood.max',10,8);advisor_history.finish(bad,'9','verified')
    pending=advisor_history.begin(KEY,'flood.max',10,8);advisor_history.finish(pending,None,'unconfirmed')
    p.sync_verified(KEY);assert not p.markers(KEY)
    with advisor_history.database() as db:
        db.execute("INSERT INTO changes VALUES(?,?,?,?,?,?,?,?)",(123,NOW-2,OTHER,'tx.power','10','12','12','verified'))
    p.sync_verified(OTHER);assert len(p.markers(OTHER))==1
    # Clearing the optimizer audit does not destroy the permanent local journal.
    advisor_history.clear_verified_flood(OTHER)
    assert len(p.markers(OTHER))==1


def test_companion_no_double_count_stats_independent_of_optimizer_and_collisions(stores,monkeypatch):
    for tracked in (False,True):packet(NOW-10,tracked=tracked)
    row=p.passive(KEY,NOW-3600,NOW,3600)
    assert row['copies']==1 and row['unique']==1 and row['routes']==1 and row['network']==1
    assert row['source'].startswith('Repeater Statistics')
    packet(NOW-5,tracked=True,ambiguous=1)
    assert p.passive(KEY,NOW-3600,NOW,3600)['ambiguous']==1
    # Local Statistics still contributes when the Optimizer stream is empty.
    with sqlite3.connect(passive_stats.STATS_PATH) as db:db.execute('DELETE FROM network_observations')
    row=p.passive(KEY,NOW-3600,NOW,3600);assert row['copies']==1 and row['network'] is None
    packet(NOW-10,key=OTHER)
    monkeypatch.setattr(passive_stats,'known_repeaters',lambda:[{'public_key':KEY},{'public_key':KEY[:2]+'ff'*31}])
    packet(NOW-15)
    row=p.passive(KEY,NOW-100,NOW-8,3600)
    # Tracked stream's historical ambiguity is retained, never added to the duplicate stream.
    assert row['copies']==1
    with sqlite3.connect(passive_stats.STATS_PATH) as db:db.execute('DELETE FROM observations')
    row=p.passive(KEY,NOW-100,NOW,3600);assert row['copies']==0 and row['ambiguous']==1


def test_exact_comparison_windows_nonoverlap_zero_and_missing_baselines(stores):
    at=NOW-2*p.DAY
    ident=p.marker_change(KEY,'create',{'description':'Antenna','at':at},now=NOW)
    p.marker_change(KEY,'create',{'description':'Firmware update','at':at+20},now=NOW)
    packet(at-10,digest='before');packet(at,digest='after1');packet(at+10,digest='after2')
    # Rolling hourly samples crossing the change are excluded. Dense samples are not added.
    for offset,value in [(-3600,5),(-1800,99),(30,999),(3600,10),(5400,999),(7200,20)]:
        d=copy.deepcopy(DATA);d['detail']['stat']['relayCount1h']=value;p.record_analyzer(KEY,at+offset,d)
    marker=next(m for m in p.markers(KEY) if m['id']==ident)
    result=p.comparison(KEY,marker,1,NOW,p.markers(KEY))
    b,a=(result['windows'][n] for n in ('before','after'))
    assert b['values']['companion_packets']==1 and a['values']['companion_packets']==2
    assert b['end']==a['start']==at and b['end']-b['start']==a['end']-a['start']==p.DAY
    assert b['values']['analyzer_hourly_relays_mean']==5
    assert a['values']['analyzer_hourly_relays_mean']==15
    assert result['differences']['companion_packets']['percent']==100
    assert result['differences']['analyzer_hourly_relays_mean']['percent']==200
    assert len(result['overlapping_markers'])==1 and any('incomplete' in w for w in result['warnings'])
    assert 'Correlation does not prove' in result['interpretation']
    empty=p.comparison(OTHER,marker,7,NOW,[])
    assert empty['differences']['companion_packets']['percent'] is None
    assert any('still being collected' in w for w in empty['warnings'])
    # Measured zero baseline cannot produce an infinite percentage.
    packet(at-10,key=OTHER)
    with sqlite3.connect(passive_stats.STATS_PATH) as db:db.execute('DELETE FROM network_observations WHERE route=?',(KEY[:2],))
    assert p.comparison(KEY,marker,1,NOW,[])['differences']['companion_packets']['percent'] is None


def test_optimizer_neighbor_history_reused(stores):
    with sqlite3.connect(optimizer_store.FILE) as db:
        db.execute("INSERT INTO snapshots VALUES(1,?,?,'manual',1,1)",(KEY,NOW-100))
        db.execute('INSERT INTO neighbors VALUES(1,?,5,10)',(OTHER,))
    data=p.overview(KEY,7,NOW)
    assert data['optimizer_neighbors']['observed']==1
    assert any(b['optimizer_neighbors']==1 for b in data['timeline'])


def test_api_guards_local_crud_missing_storage_and_windows(stores,monkeypatch):
    import meshcorestation.analyzer as analyzer
    monkeypatch.setattr(analyzer.service,'cached',lambda key:None)
    app=Flask(__name__);register_performance_routes(app);c=app.test_client();headers={'X-Meshcore-Control':'1'}
    assert c.get('/api/repeater-performance?public_key='+KEY).status_code==403
    assert c.post('/api/repeater-performance',headers={**headers,'Origin':'https://elsewhere'},json={}).status_code==403
    saved=c.post('/api/repeater-performance',headers=headers,json={'public_key':KEY,'action':'create','description':'Firmware update','at':1000})
    assert saved.status_code==200
    ident=saved.json['id']
    for days in (1,7,30):
        for compare_days in (1,3,7):
            result=c.get(f'/api/repeater-performance?public_key={KEY}&days={days}&marker_id={ident}&compare_days={compare_days}',headers=headers)
            assert result.status_code==200 and result.json['comparison']['days']==compare_days
            assert result.headers['Cache-Control']=='no-store'
    for suffix in ('&days=2','&compare_days=2','&marker_id=0','&days=nan','&url=x'):
        assert c.get('/api/repeater-performance?public_key='+KEY+suffix,headers=headers).status_code==400
    assert c.post('/api/repeater-performance',headers=headers,data='bad',content_type='application/json').status_code==400
    assert c.post('/api/repeater-performance',headers=headers,data='x'*4097,content_type='application/json').status_code==400
    assert c.get(f'/api/repeater-performance?public_key={OTHER}&marker_id={ident}',headers=headers).status_code==400
    monkeypatch.setattr(p,'FILE',stores) # Directory instead of a writable database.
    assert c.get('/api/repeater-performance?public_key='+KEY,headers=headers).status_code==503


def test_analyzer_history_only_successful_refreshes_and_removal(stores):
    # Reuse the transport fixture's eight actual responses.
    from test_analyzer import NAMES,BODIES
    calls=[];clock=[NOW]
    def fetch(url,headers,timeout):
        name=next(k for k in NAMES if analyzer_path(k) in url);calls.append(name);return 200,{},BODIES[name]
    from meshcorestation.analyzer import ENDPOINTS
    def analyzer_path(name):return ENDPOINTS[name].format(key=KEY)
    service=AnalyzerService(stores/'cache.db',fetch,lambda:clock[0])
    assert service.snapshot(KEY)['state']=='available'
    assert len(p.measurements(KEY,NOW-1,NOW+1))==1
    service.snapshot(KEY);assert len(calls)==8
    clock[0]+=901
    assert service.snapshot(KEY)['state']=='available'
    assert len(p.measurements(KEY,NOW-1,NOW+1000))==2
    clock[0]+=901;service.fetch=lambda *a:(403,{},b'')
    assert service.snapshot(KEY)['state']=='blocked'
    assert len(p.measurements(KEY,NOW-1,NOW+2000))==2
    service.remove(KEY);assert p.measurements(KEY,0,NOW+1000)==[]


def test_history_failure_does_not_break_monitoring_snapshot(stores,monkeypatch):
    from test_analyzer import NAMES,BODIES
    from meshcorestation.analyzer import ENDPOINTS
    def fetch(url,headers,timeout):
        name=next(k for k in NAMES if ENDPOINTS[k].format(key=KEY) in url)
        return 200,{},BODIES[name]
    def failed(*args):raise sqlite3.OperationalError('disk full')
    monkeypatch.setattr(p,'record_analyzer',failed)
    service=AnalyzerService(stores/'cache.db',fetch,lambda:NOW)
    result=service.snapshot(KEY)
    assert result['state']=='available' and result['data']['detail']['stat']['relayCount24h']==107
    assert 'could not be saved' in result['history_error'] and service.cached(KEY)
