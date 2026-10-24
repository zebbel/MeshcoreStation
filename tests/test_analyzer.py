"""Captured shapes verify offline behavior, never access permission or live service."""
import copy
import json
import sqlite3
import threading
from pathlib import Path
from urllib.error import URLError

import pytest
from flask import Flask
from meshcorestation import analyzer as a
from meshcorestation.web import analyzer_api

FIXTURES=Path(__file__).parent/'fixtures/analyzer'
MANIFEST=json.loads((FIXTURES/'manifest.json').read_text())
KEY=MANIFEST['repeater_public_key']
NAMES={'detail':'node_detail_24h.json','neighbors':'node_neighbors.json','reach':'node_reach_1d.json',
       'metrics':'graph_metrics.json','clock':'clock_skew_24h.json','direct':'direct_packets_24h_empty.json',
       'beacons':'channel_beacons_720h_empty.json','sensors':'channel_sensors_720h_empty.json'}
BODIES={name:(FIXTURES/'responses'/file).read_bytes() for name,file in NAMES.items()}


@pytest.fixture
def client(tmp_path):
    calls=[];now=[1000.]
    def fetch(url,headers,timeout):
        name=next(n for n,t in a.ENDPOINTS.items() if url==a.HOST+t.format(key=KEY))
        calls.append((name,headers,timeout))
        return 200, {'ETag':'"'+name+'"'}, BODIES[name]
    service=a.AnalyzerService(tmp_path/'cache.db',fetch,lambda:now[0],lambda:True)
    return service,calls,now


def test_captured_formats_all_eight_and_semantics(client):
    service,calls,_=client
    r=service.snapshot(KEY)
    assert r['state']=='available' and not r['live_verified'] and r['experimental']
    assert len(calls)==8
    data=r['data']
    assert data['detail']['stat']['relayCount24h']==107
    assert len(data['detail']['pathsThroughNode'])==50
    assert len(data['detail']['relayTimeline'])==23
    assert data['detail']['heardBy']==[]
    assert len(data['reach']['neighbourList'])==16
    assert data['reach']['twoWayCount']==4
    assert data['reach']['directObservers']==0
    assert all(n['Provenance']=='inferred-only' and n['SNR'] is None for n in data['neighbors'])
    assert data['direct']['rows']==[] and data['beacons']['beacons']==[] and data['sensors']['readings']==[]


def test_cache_manual_refresh_restart_and_rolling_counts(client):
    service,calls,now=client
    assert service.snapshot(KEY,cache_only=True)['data'] is None and not calls
    first=service.snapshot(KEY)
    now[0]+=299
    assert service.snapshot(KEY)['state']=='cached' and len(calls)==8
    second=service.snapshot(KEY,force=True)
    assert len(calls)==16 and second['data']==first['data']
    now[0]+=300
    saved=service.snapshot(KEY,cache_only=True)
    assert saved['stale'] and len(calls)==16
    other=a.AnalyzerService(service.path,service.fetch,lambda:now[0],lambda:True)
    assert other.snapshot(KEY,cache_only=True)['data']==first['data']
    other.snapshot(KEY)
    assert len(calls)==24
    assert calls[-1][1]=={'If-None-Match':'"sensors"'}


def test_conditional_not_modified(client):
    service,calls,now=client
    initial=service.snapshot(KEY)
    service.fetch=lambda *args:(304,{},b'')
    now[0]+=301
    r=service.snapshot(KEY)
    assert r['state']=='available' and r['data']==initial['data'] and r['fetched_at']==now[0]


@pytest.mark.parametrize('status,state,attempts',[(403,'blocked',1),(429,'rate_limited',1),(500,'unavailable',1),(503,'unavailable',2),(404,'unavailable',1),(302,'unavailable',1)])
def test_http_failures_preserve_snapshot(client,status,state,attempts):
    service,_,now=client
    original=service.snapshot(KEY);now[0]+=301;calls=[]
    service.fetch=lambda *args:(calls.append(args) or (status,{},b'<html>blocked</html>'))
    r=service.snapshot(KEY)
    assert r['state']==state and r['stale'] and r['data']==original['data']
    assert r['fetched_at']==original['fetched_at'] and len(calls)==attempts
    if status in (403,429):
        service.snapshot(KEY,force=True);service.snapshot('ab'*32,force=True)
        assert len(calls)==1  # cooldown applies across keys, including manual refresh


def test_timeout_preserves_cache(client):
    service,_,now=client
    original=service.snapshot(KEY);now[0]+=301
    def fail(*args):raise a.AnalyzerError('unavailable','Request timed out.')
    service.fetch=fail
    r=service.snapshot(KEY)
    assert r['state']=='unavailable' and r['data']==original['data'] and r['stale']


@pytest.mark.parametrize('body',[b'not json',b'null',b'[]',b'{}',b'{"node":{},"stat":{}}',b'{"node":NaN}'])
def test_malformed_empty_envelopes_are_failures(client,body):
    service,_,_=client;service.fetch=lambda *args:(200,{},body)
    result=service.snapshot(KEY)
    assert result['state']=='invalid' and result['data'] is None and result['fetched_at'] is None


@pytest.mark.parametrize('name',list(NAMES))
def test_nested_bad_types_rejected(name):
    data=json.loads(BODIES[name])
    if name=='neighbors':data=[{'SNR':{'fake':10}}]
    elif name=='detail':data['relayTimeline']=[{'count':'twelve'}]
    elif name=='reach':data['neighbourList']=[{'weHear':[]}]
    elif name=='metrics':data['degree']='12'
    elif name=='clock':data['samples']=['bad']
    else:data[next(k for k in ('rows','beacons','readings') if k in data)]=[False]
    with pytest.raises(a.AnalyzerError):a.validate(name,json.dumps(data).encode(),KEY)


def test_oversized_response(client):
    service,_,_=client;service.fetch=lambda *args:(200,{},b' '*(a.MAX_BODY+1))
    assert service.snapshot(KEY)['state']=='invalid'


@pytest.mark.parametrize('key',['',None,'ab','../api','a'*63,'g'*64,'a'*64+'?x=1','https://example.com'])
def test_invalid_keys_never_fetch(client,key):
    service,calls,_=client
    with pytest.raises(ValueError):service.snapshot(key)
    assert not calls


def test_disabled_by_default_and_no_fixture_production_fallback(tmp_path,monkeypatch):
    monkeypatch.delenv('MESHCORESTATION_ANALYZER_AUTHORIZED',raising=False)
    def no(*args):pytest.fail('Unexpected remote access')
    service=a.AnalyzerService(tmp_path/'cache.db',no)
    r=service.snapshot(KEY,force=True)
    assert r['state']=='disabled' and r['data'] is None and not r['live_verified']


def test_singleflight_and_per_key_isolation(client):
    service,_,_=client
    started=threading.Event();release=threading.Event();fetch=service.fetch
    def wait(*args):
        started.set();assert release.wait(5);return fetch(*args)
    service.fetch=wait;out=[]
    worker=threading.Thread(target=lambda:out.append(service.snapshot(KEY)))
    worker.start();assert started.wait(5)
    try:
        assert service.snapshot(KEY)['state']=='busy'
        assert service.snapshot('ab'*32)['data'] is None
    finally:release.set();worker.join(5)
    assert out[0]['state']=='available'


def test_wrong_identity_partial_failure_not_saved(client):
    service,_,_=client
    original=service.snapshot(KEY);fetch=service.fetch
    def fail(url,*args):
        if '/reach?' in url:return 200,{},b'{"neighbourList":false}'
        return fetch(url,*args)
    service.fetch=fail
    r=service.snapshot(KEY,force=True)
    assert r['state']=='invalid' and service.cached(KEY)[1]==original['data']
    with pytest.raises(a.AnalyzerError):a.validate('detail',BODIES['detail'],'ab'*32)


def test_local_api_policy_and_flags(client,monkeypatch):
    service,calls,_=client;monkeypatch.setattr(analyzer_api,'service',service)
    app=Flask(__name__);analyzer_api.register_analyzer_routes(app);http=app.test_client()
    assert http.get('/api/repeater-network?public_key='+KEY).status_code==403
    headers={'X-Meshcore-Control':'1'}
    assert http.get('/api/repeater-network?public_key='+KEY+'&url=https://other',headers=headers).status_code==400
    assert http.get('/api/repeater-network?public_key='+KEY+'&refresh=bad',headers=headers).status_code==400
    assert http.get('/api/repeater-network?public_key=bad',headers=headers).status_code==400
    r=http.get('/api/repeater-network?public_key='+KEY+'&cache_only=1',headers=headers)
    assert r.status_code==200 and not calls and r.headers['Cache-Control']=='no-store'
    assert http.get('/api/repeater-network?public_key='+KEY,headers=headers).json['state']=='available'


def test_v3_database_untouched_by_cache(client,tmp_path):
    # New cache lives separately; no change or destructive migration of V3 data.
    db=sqlite3.connect(tmp_path/'v3.db');db.execute('CREATE TABLE logger(id INTEGER PRIMARY KEY,message TEXT)')
    db.execute("INSERT INTO logger VALUES (1,'legacy')");db.commit()
    client[0].snapshot(KEY)
    assert db.execute('SELECT * FROM logger').fetchall()==[(1,'legacy')]
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    db.close()


def test_successful_empty_windows(client):
    service,calls,_=client
    empty=copy.deepcopy({n:json.loads(b) for n,b in BODIES.items()})
    empty['detail']['stat']={}
    for k,v in empty['detail'].items():
        if isinstance(v,list):empty['detail'][k]=[]
    empty['neighbors']=[];empty['reach']['neighbourList']=[]
    empty['reach']['twoWayCount']=0;empty['reach']['directObservers']=0
    empty['metrics']['degree']=0
    fetch=service.fetch
    def respond(url,headers,timeout):
        fetch(url,headers,timeout)
        name=calls[-1][0]
        return 200,{},json.dumps(empty[name]).encode()
    service.fetch=respond
    r=service.snapshot(KEY)
    assert r['state']=='available' and r['data']['neighbors']==[]
    assert r['data']['detail']['stat']=={}  # absent metrics remain unknown, never guessed as zero


def test_transport_timeout_redirects_and_request_identity(monkeypatch):
    seen=[]
    class Opener:
        def open(self,req,timeout):
            seen.append((req,timeout));raise URLError(TimeoutError())
    monkeypatch.setattr(a,'build_opener',lambda handler:Opener())
    with pytest.raises(a.AnalyzerError,match='timed out'):a.transport(a.HOST+'/api/example',{},3)
    req,timeout=seen[0]
    assert timeout==3 and not req.has_header('Cookie') and not req.has_header('Authorization')
    assert req.get_header('User-agent').startswith('MeshcoreStation/')
    assert a.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://elsewhere') is None


def test_remove_during_refresh_cannot_restore_deleted_snapshot(client):
    service,_,_=client
    service.snapshot(KEY);fetch=service.fetch
    def remove_while_fetching(*args):
        service.remove(KEY)
        return fetch(*args)
    service.fetch=remove_while_fetching
    r=service.snapshot(KEY,force=True)
    assert r['state']=='removed' and r['data'] is None
    assert service.cached(KEY) is None
