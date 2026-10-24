"""Values, coverage and comparisons are derived from stored observations only."""
import copy
import sqlite3
import pytest
from test_performance import stores,KEY,OTHER,DATA,packet
from meshcorestation.storage import performance_store as p, passive_stats
from meshcorestation.storage.performance_view import dashboard, comparable_companion
from test_analyzer_collector import data_at, NOW


def sample(at,count=3,pairs=21,sole=1,two_way=None):
    d=data_at(at,count=count)
    d['detail']['stat'].update(pairsServed=pairs,pairsSole=sole)
    p.record_analyzer(KEY,at,d)
    if two_way is not None:
        with p.database() as db:db.execute('UPDATE measurements SET two_way=? WHERE public_key=? AND at=?',(two_way,KEY,at))


def companion_bucket(at,involved,total):
    for i in range(total):packet(at+10+i,key=KEY if i<involved else OTHER,digest=str(at)+'-'+str(i))
    # Copies from the managed stream are deliberately different: they MUST NOT
    # enter the comparable traffic chart or its normalization.
    for i in range(3):packet(at+1+i,tracked=True)


def test_cards_fixed_rolling_period_and_original_values(stores):
    sample(NOW)
    for days in (1,7,30):
        v=dashboard(KEY,NOW-days*p.DAY,NOW,3600)
        c=v['cards']
        assert c['at']==NOW and c['period_seconds']==86400
        assert c['relay_24h']==107 and c['pairs']==21 and c['sole_pairs']==1
        assert c['two_way']==4 and c['neighbors']==14 and c['two_way_percent']==pytest.approx(100*4/14)
        assert v['end']-v['start']==days*86400
    assert dashboard(OTHER,NOW-86400,NOW,3600)['cards']['relay_24h'] is None


def test_older_database_gains_nullable_sole_pairs_without_loss(stores):
    with sqlite3.connect(p.FILE) as db:
        db.execute('CREATE TABLE measurement_details(public_key TEXT,at REAL,pairs REAL,routes INTEGER,betweenness REAL,graph_rank REAL,PRIMARY KEY(public_key,at))')
        db.execute('INSERT INTO measurement_details VALUES(?,?,?,?,?,?)',(KEY,NOW,21,50,.0004,5))
    with p.database() as db:
        row=dict(db.execute('SELECT * FROM measurement_details').fetchone())
        assert row['pairs']==21 and row['sole_pairs'] is None
    # An actual saved response may backfill that same snapshot's missing field.
    sample(NOW)
    assert dashboard(KEY,NOW-86400,NOW,3600)['cards']['sole_pairs']==1
    assert p.measurements(KEY,NOW-1,NOW+1)[0]['relay_24h']==107


def test_same_companion_stream_normalization_and_gaps(stores):
    start=NOW-4*3600
    companion_bucket(start,2,4);companion_bucket(start+3600,4,4)
    companion_bucket(start+3*3600,1,8)
    r=comparable_companion(KEY,start,NOW,3600)
    points=r['timeline']
    assert r['baseline']=={'at':start,'copies':2,'network':4}
    assert [(b['repeater_index'],b['mesh_index']) for b in points]==[(100,100),(200,100),(None,None),(50,200)]
    assert r['available']==3 and r['expected']==4
    assert points[0]['copies']==2 # Not 2 + tracked copies!
    assert r['source']=='Companion network path observations'


def test_partial_zero_and_ambiguous_baselines_are_not_invented(stores,monkeypatch):
    start=NOW-3*3600
    companion_bucket(start,0,3);companion_bucket(start+3600,2,4)
    r=comparable_companion(KEY,start+60,NOW,3600)
    assert r['timeline'][0]['repeater_index'] is None
    assert r['baseline']['at']==start+3600
    monkeypatch.setattr(passive_stats,'known_repeaters',lambda:[{'public_key':KEY},{'public_key':KEY[:2]+'ff'*31}])
    r=comparable_companion(KEY,start,NOW,3600)
    assert r['baseline'] is None and all(b['repeater_index'] is None for b in r['timeline'])
    assert r['timeline'][1]['copies'] is None and r['timeline'][1]['ambiguous']==2


def test_complete_four_domain_assessment_and_mesh_context(stores):
    start=NOW-86400
    for hour in range(24):companion_bucket(start+hour*3600,2 if hour<12 else 4,4)
    sample(start+6*3600,count=2,pairs=10,sole=1,two_way=2)
    sample(start+18*3600,count=4,pairs=20,sole=2,two_way=4)
    # Record the fully completed last hours too; overlapping responses replace.
    final=data_at(NOW,count=4)
    final['detail']['stat'].update(pairsServed=20,pairsSole=2)
    for row in final['detail']['relayTimeline']:
        from datetime import datetime
        if datetime.fromisoformat(row['bucket']).timestamp()<start+12*3600:row['count']=2
    p.record_analyzer(KEY,NOW,final)
    v=dashboard(KEY,start,NOW,3600)
    a=v['assessment']
    assert all(r['status']=='Observed change' for r in a.values())
    assert a['forwarding']['changes']['hourly_relays']['percent']==100
    assert 'greater observed contribution' in v['interpretation']
    assert a['relative']['changes']['copies']['percent']==100
    assert a['relative']['changes']['network']['percent']==0
    assert 'faster than' in a['relative']['explanation']
    assert a['connectivity']['changes']['two_way']['before']==2
    assert a['connectivity']['changes']['two_way']['after']==4
    assert a['routing']['changes']['pairs']['percent']==100
    assert a['routing']['changes']['sole_pairs']['percent']==100
    assert a['forwarding']['coverage']['available']==a['forwarding']['coverage']['expected']==[12,12]
    assert 'causation' in v['caution']


def test_missing_hours_snapshots_and_older_sole_values_withhold_assessment(stores):
    sample(NOW-12*3600)
    with p.database() as db:
        db.execute('UPDATE measurement_details SET sole_pairs=NULL')
        db.execute('DELETE FROM hourly_relays WHERE at=?',(NOW-13*3600,))
    v=dashboard(KEY,NOW-86400,NOW,3600)
    assert v['overall']=='Insufficient Data'
    assert all(a['status']=='Insufficient Data' for a in v['assessment'].values())
    assert any(b['hourly_relays'] is None for b in v['forwarding'])
    assert v['snapshots'][-1]['pairs'] is not None and v['snapshots'][-1]['sole_pairs'] is None
    assert v['cards']['sole_pairs'] is None


@pytest.mark.parametrize('days',[1,3,7])
def test_change_dashboard_equal_windows_original_timestamps_and_future(days,stores):
    marker_at=NOW-86400+300
    ident=p.marker_change(KEY,'create',{'description':'Antenna','at':marker_at},now=NOW)
    sample(NOW-86400);sample(NOW)
    result=p.overview(KEY,7,NOW,marker_id=ident,compare_days=days)
    v=result['comparison']['dashboard']
    assert v['split']==marker_at
    assert v['split']-v['start']==v['end']-v['split']==days*86400
    assert any(m['id']==ident and m['at']==marker_at for m in result['markers'])
    if v['end']>NOW:
        assert all(a['status']=='Insufficient Data' for a in v['assessment'].values())
    assert all(r['stamp']%3600==0 for r in v['forwarding'])
    assert result['dashboard']['cards']['at']==NOW


def test_snapshot_gaps_do_not_repeat_previous_measurements(stores):
    start=NOW-3*86400
    sample(start+1);sample(start+36*3600+1,pairs=9,sole=0)
    v=dashboard(KEY,start,NOW,21600)
    assert len(v['snapshots'])==6
    assert v['snapshots'][0]['pairs']==21 and v['snapshots'][3]['pairs']==9
    assert v['snapshots'][3]['sole_pairs']==0
    assert all(v['snapshots'][i]['pairs'] is None for i in (1,2,4,5))
    assert v['snapshots'][0]['stamp']==start+1


@pytest.mark.parametrize('before,after,mesh_before,mesh_after,expected',[(4,2,4,2,'same rate'),(4,2,4,4,'slower than'),(4,4,4,8,'slower than'),(2,4,4,8,'same rate'),(4,2,8,2,'slower decline')])
def test_relative_assessment_accounts_for_mesh_traffic(stores,before,after,mesh_before,mesh_after,expected):
    start=NOW-86400
    for h in range(24):companion_bucket(start+h*3600,before if h<12 else after,mesh_before if h<12 else mesh_after)
    v=dashboard(KEY,start,NOW,3600)
    relative=v['assessment']['relative']
    assert relative['status']=='Observed change'
    assert expected in relative['explanation']
    assert relative['changes']['copies']['percent']==pytest.approx(100*(after-before)/before)
    assert relative['changes']['network']['percent']==pytest.approx(100*(mesh_after-mesh_before)/mesh_before)


def test_zero_baseline_and_trim_warnings_prevent_relative_conclusions(stores):
    start=NOW-86400
    for h in range(24):companion_bucket(start+h*3600,0 if h<12 else 1,4)
    v=dashboard(KEY,start,NOW,3600)
    assert v['assessment']['relative']['status']=='Insufficient Data'
    assert v['assessment']['relative']['changes']['copies']['percent'] is None
    with sqlite3.connect(passive_stats.STATS_PATH) as db:db.execute('UPDATE health SET trimmed_at=? WHERE id=1',(NOW-10,))
    assert 'retention' in dashboard(KEY,start,NOW,3600)['assessment']['relative']['explanation']


def test_missing_companion_bucket_never_becomes_zero_or_reliable_change(stores):
    start=NOW-86400
    for h in range(24):
        if h!=13:companion_bucket(start+h*3600,1,2)
    v=dashboard(KEY,start,NOW,3600)
    assert v['companion']['timeline'][13]['copies'] is None
    assert v['companion']['timeline'][13]['repeater_index'] is None
    assert v['assessment']['relative']['status']=='Insufficient Data'
    assert v['assessment']['relative']['coverage']=={'available':[12,11],'expected':[12,12]}
    assert v['assessment']['relative']['changes']=={}
