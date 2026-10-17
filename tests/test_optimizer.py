"""Repeater Optimizer: passive capture, policy and explanation tests."""
import time
from flask import Flask
from meshcorestation.storage import optimizer_store,passive_stats
from meshcorestation.optimizer_engine import analyze,compare_history
from meshcorestation.web import optimizer_api

KEY='ab'*32

def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(optimizer_store,'FILE',tmp_path/'opt.db')
    monkeypatch.setattr(passive_stats,'STATS_PATH',tmp_path/'passive.db')
    optimizer_store.initialize()
    passive_stats.initialize()

def test_opt_in_polling_defaults_and_snapshots(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    assert optimizer_store.profile(KEY)['polling']=='manual'
    assert optimizer_store.due() is None
    assert not optimizer_store.claim_poll(KEY)
    now=time.time()
    profile=optimizer_store.update_profile(KEY,'hybrid','12h')
    assert profile['next_poll']>now+43190
    assert optimizer_store.due(now+43180) is None
    assert optimizer_store.due(now+43300)['public_key']==KEY
    assert optimizer_store.claim_poll(KEY,now+43300)
    assert optimizer_store.due(now+43301) is None
    result=optimizer_store.save_neighbors(KEY,
        {'neighbours':[{'pubkey':'cd'*6,'snr':5.5,'secs_ago':120}],
         'neighbours_count':1},'manual')
    assert result['complete']
    assert optimizer_store.snapshots(KEY)[0]['neighbors'][0]['snr']==5.5
    optimizer_store.update_profile(KEY,'hybrid','manual')
    assert optimizer_store.due(now+864000) is None

def test_passive_network_observations_include_other_repeaters(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    now=time.time()
    with passive_stats.connect() as db:
        db.execute("""INSERT INTO network_observations
            (at,kind,scoped,path_len,hash_size,route,digest,rssi,snr)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (now-3600,5,0,2,1,'cd|ef','fingerprint',-99,3))
        db.commit()
    data=passive_stats.network_snapshot(KEY,7)
    assert data['copies']==1
    assert data['matching_copies']==0
    assert data['unscoped']==1
    assert not data['scope']['unscoped']['hist']
    normalized=passive_stats.normalize(dict(route_type=1,payload_type=5,
        path_len=2,path_hash_size=1,path='abcd',pkt_payload=b'private'))
    assert normalized['path']==['ab','cd']
    assert normalized['digest']!='private'
    assert 'private' not in str(normalized)

def test_observed_hop_histograms_and_recommendations(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    now=time.time()
    rows=[(now-8*86400,5,1,3,1,'ab|cd|ef','early',-80,5)]
    for i in range(150):
        rows.append((now-(1+i%5)*86400,5,i%2,3,1,'ab|cd|ef',str(i),-90,5))
    with passive_stats.connect() as db:
        db.executemany("""INSERT INTO network_observations
            (at,kind,scoped,path_len,hash_size,route,digest,rssi,snr)
            VALUES(?,?,?,?,?,?,?,?,?)""",rows)
        db.commit()
    stats=passive_stats.network_snapshot(KEY,7)
    assert stats['matching_copies']==150
    assert stats['scope']['scoped']['hist'][3]==75
    assert stats['scope']['unscoped']['hist'][3]==75
    assert stats['active_days']>=3
    optimizer_store.update_profile(KEY,'local','manual')
    optimizer_store.save_neighbors(KEY,{'neighbours':[{'pubkey':'cd'*6,'snr':5,'secs_ago':50}],
                                        'neighbours_count':1})
    response=analyze(stats,optimizer_store.profile(KEY),optimizer_store.snapshots(KEY),
                     {'flood.max':'32','flood.max.unscoped':'15'})
    assert response['recommendations'][0]['suggested']==5
    assert response['recommendations'][1]['suggested']==5
    assert all(row['confidence']=='experimental' for row in response['recommendations'])
    missing=analyze(stats,{'role':'unknown'},[],{})
    assert not any(row['can_apply'] for row in missing['recommendations'])

def test_before_after_is_observational_not_causal(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    now=time.time()
    at=now-26*3600
    data=[]
    for base in [at-86400,at+3600]:
        for i in range(120):
            data.append((base+i,5, i%2,2,1,'ab|cd',str(i if base<at else i//2),-80,2))
    with passive_stats.connect() as db:
        db.executemany("""INSERT INTO network_observations
            (at,kind,scoped,path_len,hash_size,route,digest,rssi,snr)
            VALUES(?,?,?,?,?,?,?,?,?)""",data)
        db.commit()
    history=[dict(id=1,at=at,field='flood.max',before_value='32',
                  requested='12',actual='12',status='verified')]
    result=compare_history(KEY,history,now)['1']
    assert result['status']=='descriptive'
    assert result['before']['copies']==result['after']['copies']==120
    assert result['delta']['repeated_pct']>0
    assert 'no causal' in result['notes'][0]

def test_api_never_uses_radio_for_analysis(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    app=Flask(__name__);optimizer_api.register_optimizer_routes(app)
    client=app.test_client()
    headers={'X-Meshcore-Control':'1'}
    assert client.get('/api/repeater-optimizer?public_key='+KEY).status_code==403
    response=client.get('/api/repeater-optimizer?public_key='+KEY,headers=headers)
    assert response.status_code==200
    assert response.json['profile']['polling']=='manual'
    assert response.json['analysis']['recommendations'][0]['suggested'] is None
    monkeypatch.setattr(optimizer_api.bridge,'request',lambda payload,timeout=5: {'ok':True})
    stored=client.post('/api/repeater-optimizer',headers=headers,json={
        'action':'profile','public_key':KEY,'role':'regional','polling':'24h'})
    assert stored.status_code==200
    assert optimizer_store.profile(KEY)['polling']=='24h'



def test_clear_verified_changes_scoped_to_selected_repeater(tmp_path, monkeypatch):
    """Clear derived comparison history, not packet observations or other audits."""
    from meshcorestation.storage import advisor_history
    setup(tmp_path,monkeypatch)
    monkeypatch.setattr(advisor_history,'FILE',tmp_path/'history.db')
    other='cd'*32
    with advisor_history.database() as db:
        rows=[
            (KEY,'flood.max','verified'),
            (KEY,'flood.max.unscoped','verified'),
            (KEY,'flood.max','pending / outcome unknown'),
            (KEY,'loop.detect','verified'),
            (other,'flood.max','verified'),
        ]
        for key,field,status in rows:
            db.execute("""INSERT INTO changes(at,public_key,field,before_value,requested,actual,status)
                 VALUES(?,?,?,?,?,?,?)""",(time.time(),key,field,'8','5','5',status))
    with passive_stats.connect() as db:
        db.execute("""INSERT INTO network_observations
            (at,kind,scoped,path_len,hash_size,route,digest,rssi,snr)
            VALUES(?,?,?,?,?,?,?,?,?)""",(time.time(),5,1,1,1,'ab','digest',-80,2))
        db.commit()
    app=Flask(__name__)
    optimizer_api.register_optimizer_routes(app)
    client=app.test_client()
    headers={'X-Meshcore-Control':'1'}
    request_data={'action':'clear_history','public_key':KEY,'session':'test-admin'}
    refused=client.post('/api/repeater-optimizer',json=request_data,headers=headers)
    assert refused.status_code==403
    assert len(advisor_history.recent(KEY))==4
    captured=[]
    def locally_authorized(payload,timeout=5):
        captured.append(payload)
        return {'ok':payload['operation']=='optimizer_authorize'
                and payload['public_key']==KEY and payload['session']=='test-admin'}
    monkeypatch.setattr(optimizer_api.bridge,'request',locally_authorized)
    # A valid administrator session alone is not enough for deletion.
    assert client.post('/api/repeater-optimizer',json=request_data,headers=headers).status_code==400
    request_data['confirm']=True
    cleared=client.post('/api/repeater-optimizer',json=request_data,headers=headers)
    assert cleared.status_code==200
    assert cleared.json['removed']==2
    assert len(captured)==2 and all(item['operation']=='optimizer_authorize' for item in captured)
    assert {(entry['field'],entry['status']) for entry in advisor_history.recent(KEY)}=={
        ('flood.max','pending / outcome unknown'),('loop.detect','verified')}
    assert len(advisor_history.recent(other))==1
    assert passive_stats.network_snapshot(KEY,1)['copies']==1
    # Repeating the clearing operation does not damage unrelated records.
    assert client.post('/api/repeater-optimizer',json=request_data,headers=headers).json['removed']==0
