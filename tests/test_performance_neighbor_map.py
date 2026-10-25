"""Focused API checks: cached data only, honest periods and unavailable states."""
import copy
import time
from flask import Flask
from test_performance import stores,KEY,OTHER,DATA
from meshcorestation.web.performance_api import register_performance_routes,saved_neighbor_map


def test_saved_map_projection_and_empty_unavailable_distinction():
    assert not saved_neighbor_map(None)['available']
    assert not saved_neighbor_map((10,{'detail':{}},{}))['available']
    data=copy.deepcopy(DATA)
    result=saved_neighbor_map((10,data,{}))
    assert result['available'] and result['hours']==24 and result['fetched_at']==10
    assert result['center']['lat']==49.640019
    assert result['neighbors'][0]['weHear']==148 and result['neighbors'][0]['theyHear']==391
    assert len(result['neighbors'])==16 and 'stat' not in result['center']
    data['reach']['neighbourList']=[]
    assert saved_neighbor_map((10,data,{}))['available']
    assert saved_neighbor_map((10,data,{}))['neighbors']==[]


def test_performance_reads_saved_map_without_external_refresh_and_switches(stores,monkeypatch):
    from meshcorestation.analyzer import service
    calls=[]
    def cached(key):
        calls.append(key)
        return (time.time()-10,DATA,{}) if key==KEY else None
    def forbidden(*args,**kwargs):raise AssertionError('Performance must not contact Analyzer')
    monkeypatch.setattr(service,'cached',cached);monkeypatch.setattr(service,'snapshot',forbidden)
    app=Flask(__name__);register_performance_routes(app);client=app.test_client();headers={'X-Meshcore-Control':'1'}
    for days in (1,7,30):
        response=client.get(f'/api/repeater-performance?public_key={KEY}&days={days}',headers=headers)
        assert response.status_code==200
        m=response.json['neighbor_map']
        assert m['hours']==24 and m['center']['id']==KEY and len(m['neighbors'])==16
        assert m['neighbors'][0]['pubkey']==DATA['reach']['neighbourList'][0]['pubkey']
    switched=client.get(f'/api/repeater-performance?public_key={OTHER}',headers=headers).json
    assert switched['neighbor_map']['available'] is False and not switched['neighbor_map']['neighbors']
    assert calls==[KEY,KEY,KEY,OTHER]
