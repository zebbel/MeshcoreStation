"""Known offline periods must not masquerade as useful optimization evidence."""
import time
from contextlib import closing
import pytest
from flask import Flask
from meshcorestation.storage import optimizer_store as store, passive_stats as stats
from meshcorestation.web import optimizer_api
from meshcorestation.optimizer_engine import analyze, compare_history

KEY='ab'*32
OTHER='cd'*32

@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'FILE',tmp_path/'optimizer.db')
    monkeypatch.setattr(stats,'STATS_PATH',tmp_path/'statistics.db')
    monkeypatch.setattr(stats,'known_repeaters',lambda:[{'public_key':KEY}])
    store.initialize();stats.initialize()
    return time.time()-100


def test_overlap_clipping_and_repeater_isolation(database):
    now=database
    store.add_downtime(KEY,now-30,now-10)
    store.add_downtime(KEY,now-20,now)
    assert store.offline_intervals(KEY,now-25,now-5)==[(now-25,now-5)]
    assert store.offline_intervals(KEY,now,now+10)==[]
    assert store.offline_intervals(OTHER,now-100,now)==[]
    row=store.downtimes(KEY)[0]
    with pytest.raises(ValueError):store.remove_downtime(OTHER,row['id'])
    assert len(store.downtimes(KEY))==2
    store.remove_downtime(KEY,row['id']);assert len(store.downtimes(KEY))==1
    store.remove_repeater(KEY);assert store.downtimes(KEY)==[]


@pytest.mark.parametrize('start,end',[(True,10),(1,float('nan')),(1,float('inf')),(20,10),(0,10),(1,1),(1,1e15)])
def test_invalid_periods_rejected(database,start,end):
    with pytest.raises(ValueError):store.add_downtime(KEY,start,end)
    assert store.downtimes(KEY)==[]


def test_downtime_excluded_from_counts_routes_days_and_charts_without_deletion(database):
    now=database
    with closing(stats.connect()) as db, db:
        for at,hops in [(now-2*86400,2),(now-86400,20),(now,3)]:
            db.execute('INSERT INTO network_observations(at,kind,scoped,path_len,hash_size,route,digest,rssi,snr) VALUES(?,?,?,?,?,?,?,?,?)',
                       (at,5,1,hops,1,'ab',str(at),-80,5))
    store.add_downtime(KEY,now-86400-10,now-86400+10)
    data=stats.network_snapshot(KEY,7)
    assert data['copies']==data['matching_copies']==2
    assert data['scope']['scoped']['hist']=={2:1,3:1}
    assert data['active_days']==2
    assert sum(row['copies'] for row in data['daily'])==2
    assert data['excluded_downtime_seconds']==20
    assert stats.network_snapshot(OTHER,7)['copies']==3
    store.remove_downtime(KEY,store.downtimes(KEY)[0]['id'])
    assert stats.network_snapshot(KEY,7)['copies']==3


def test_comparisons_reject_overlap_including_settling_period(database):
    at=database-26*3600
    change={'id':1,'at':at,'status':'verified','field':'flood.max','requested':'8','actual':'8'}
    store.add_downtime(KEY,at+10,at+100)
    result=compare_history(KEY,[change],now=at+26*3600)['1']
    assert result['status']=='unavailable' and 'downtime' in result['message']
    assert 'downtime' not in compare_history(OTHER,[change],now=at+26*3600)['1']['message']


def test_less_than_three_usable_days_blocks_trial(database):
    data={'days':7,'usable_hours':48,'copies':1000,'matching_copies':100,'active_days':4,'ambiguous':0,
          'partial':False,'collector_error':'','now':database,
          'scope':{name:{'count':100,'target':100,'hist':{2:100}} for name in ['scoped','unscoped']}}
    result=analyze(data,{'role':'local'},[{'at':database,'complete':True}],{'flood.max':'64','flood.max.unscoped':'64'})
    assert all(not row['can_apply'] for row in result['recommendations'])
    assert any('72 hours' in reason for reason in result['data_gaps'])


def test_api_downtime_writes_require_admin_and_do_not_send_radio(database,monkeypatch):
    calls=[]
    def authorize(payload,timeout=5):
        assert payload['operation']=='optimizer_authorize'
        calls.append(payload)
        return {'ok':payload['session']=='admin'}
    monkeypatch.setattr(optimizer_api.bridge,'request',authorize)
    app=Flask(__name__);optimizer_api.register_optimizer_routes(app)
    c=app.test_client();headers={'X-Meshcore-Control':'1'}
    payload={'action':'downtime','public_key':KEY,'start':database-100,'end':database}
    assert c.post('/api/repeater-optimizer',json=payload,headers=headers).status_code==403
    assert c.post('/api/repeater-optimizer',json={**payload,'session':'guest'},headers=headers).status_code==403
    assert store.downtimes(KEY)==[]
    assert c.post('/api/repeater-optimizer',json={**payload,'session':'admin'},headers=headers).status_code==200
    assert len(store.downtimes(KEY))==1
    assert len(calls)==2
