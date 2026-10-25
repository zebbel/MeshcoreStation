"""Focused API checks: local reads, explicit refresh, persistence and provider cooldowns."""
import copy
import time
import pytest
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


def refresh_client(stores,monkeypatch):
    import json
    from datetime import datetime
    from test_analyzer import BODIES
    import meshcorestation.analyzer as analyzer
    data={name:json.loads(body) for name,body in BODIES.items()}
    clock=[datetime.fromisoformat(data['detail']['relayTimeline'][-1]['bucket']).timestamp()+3600]
    monkeypatch.setattr(time,'time',lambda:clock[0])
    mode=[200];calls=[]
    def fetch(url,headers,timeout):
        name=next(name for name,path in analyzer.ENDPOINTS.items() if url==analyzer.HOST+path.format(key=KEY))
        calls.append(name)
        if mode[0]=='timeout':raise TimeoutError()
        if mode[0]=='invalid':return 200,{},b'not JSON'
        if mode[0]!=200:return mode[0],{'Retry-After':'600'},b''
        return 200,{},json.dumps(data[name]).encode()
    service=analyzer.AnalyzerService(stores/'analyzer-cache.db',fetch,lambda:clock[0])
    monkeypatch.setattr(analyzer,'service',service)
    app=Flask(__name__);register_performance_routes(app)
    return app.test_client(),service,data,clock,mode,calls


def test_explicit_refresh_updates_cache_history_cards_charts_and_map(stores,monkeypatch):
    from meshcorestation.storage import performance_store as p
    client,service,data,clock,mode,calls=refresh_client(stores,monkeypatch)
    first=service.snapshot(KEY);assert len(calls)==8
    clock[0]+=1
    assert service.snapshot(KEY)['state']=='cached' and len(calls)==8 # Shared five-minute read cache.
    data['detail']['stat']['relayCount24h']=222
    data['detail']['relayTimeline'][-1]['count']=77
    data['reach']['neighbourList'][0]['weHear']=201
    response=client.get(f'/api/repeater-performance?public_key={KEY}&refresh=1',headers={'X-Meshcore-Control':'1'})
    assert response.status_code==200 and len(calls)==16 # Explicit manual Refresh Now, even inside TTL.
    result=response.json
    assert result['analyzer_refresh']['state']=='available' and not result['analyzer_refresh']['error']
    assert result['dashboard']['cards']['relay_24h']==222
    assert any(r['hourly_relays']==77 for r in result['dashboard']['forwarding'])
    assert result['neighbor_map']['neighbors'][0]['weHear']==201
    assert service.cached(KEY)[0]==clock[0]
    assert len(p.measurements(KEY,first['fetched_at']-1,clock[0]+1))==2
    local=client.get(f'/api/repeater-performance?public_key={KEY}&days=30&refresh=0',headers={'X-Meshcore-Control':'1'}).json
    assert local['analyzer_refresh'] is None and len(calls)==16 # No refresh from period changes.
    for flag in ('2','true','url'):
        assert client.get(f'/api/repeater-performance?public_key={KEY}&refresh={flag}',headers={'X-Meshcore-Control':'1'}).status_code==400
    assert len(calls)==16


@pytest.mark.parametrize('failure',[403,429,500,'timeout','invalid'])
def test_failed_explicit_refresh_preserves_saved_data_and_provider_cooldown(stores,monkeypatch,failure):
    from meshcorestation.storage import performance_store as p
    client,service,data,clock,mode,calls=refresh_client(stores,monkeypatch)
    first=service.snapshot(KEY);clock[0]+=1;mode[0]=failure
    url=f'/api/repeater-performance?public_key={KEY}&refresh=1'
    result=client.get(url,headers={'X-Meshcore-Control':'1'}).json
    assert result['ok'] and result['analyzer_refresh']['error']
    assert result['dashboard']['cards']['relay_24h']==107
    assert result['neighbor_map']['neighbors'][0]['weHear']==148
    assert service.cached(KEY)[0]==first['fetched_at']
    assert len(p.measurements(KEY,first['fetched_at']-1,clock[0]+1))==1
    if failure in (403,429):
        before=len(calls)
        again=client.get(url,headers={'X-Meshcore-Control':'1'}).json
        assert again['analyzer_refresh']['error'] and len(calls)==before # Manual refresh cannot bypass cooldown.


def test_refresh_history_write_failure_keeps_old_history_and_reports_warning(stores,monkeypatch):
    import sqlite3
    from meshcorestation.storage import performance_store as p
    client,service,data,clock,mode,calls=refresh_client(stores,monkeypatch)
    first=service.snapshot(KEY);clock[0]+=1;data['detail']['stat']['relayCount24h']=222
    def fail(*args,**kwargs):raise sqlite3.OperationalError('disk full')
    monkeypatch.setattr(p,'record_analyzer',fail)
    response=client.get(f'/api/repeater-performance?public_key={KEY}&refresh=1',headers={'X-Meshcore-Control':'1'})
    assert response.status_code==200
    assert response.json['analyzer_refresh']['history_error']
    assert response.json['dashboard']['cards']['relay_24h']==107
    assert service.cached(KEY)[1]['detail']['stat']['relayCount24h']==222
    assert len(p.measurements(KEY,first['fetched_at']-1,clock[0]+1))==1


def test_auto_refresh_reuses_cache_then_updates_expired_history(stores,monkeypatch):
    client,service,data,clock,mode,calls=refresh_client(stores,monkeypatch)
    headers={'X-Meshcore-Control':'1'}
    url=f'/api/repeater-performance?public_key={KEY}&refresh=auto'
    # Empty history: local reads do not block on Analyzer; follow-up auto collects.
    saved=client.get(f'/api/repeater-performance?public_key={KEY}',headers=headers).json
    assert not calls and saved['days']==1
    assert client.get(url,headers=headers).json['analyzer_refresh']['state']=='available'
    assert len(calls)==8
    clock[0]+=299
    assert client.get(url,headers=headers).json['analyzer_refresh']['state']=='cached'
    assert len(calls)==8
    data['detail']['stat']['relayCount24h']=222
    clock[0]+=1
    fresh=client.get(url,headers=headers).json
    assert len(calls)==16 and fresh['dashboard']['cards']['relay_24h']==222
    clock[0]+=300;mode[0]=403
    failed=client.get(url,headers=headers).json
    assert failed['analyzer_refresh']['error'] and failed['dashboard']['cards']['relay_24h']==222
    count=len(calls)
    assert client.get(url,headers=headers).json['analyzer_refresh']['error'] and len(calls)==count
