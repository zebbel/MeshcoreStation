import asyncio
import copy
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from flask import Flask
from meshcorestation import advisor_rules as rules
from meshcorestation.storage import advisor_history as history
from meshcorestation.web import repeater_advisor as web
from meshcorestation.radio.repeater_control import RepeaterControl

KEY='ab'*32

@pytest.fixture
def settings(): return copy.deepcopy(rules.DEFAULT)

@pytest.mark.parametrize('value',[1,59,61,241,True,float('nan')])
def test_shared_advert_validation(settings,value):
    settings['targets']['advert.interval']=value
    with pytest.raises(ValueError): rules.validate(settings)


def healthy(settings):
    return {'selection':{'public_key':KEY,'since':0},'days':settings['min_days'],'copies':100,
            'usefulness':{'partial':False},'health':{'running':True,'heartbeat':time.time(),'radio':'Running'}}


def test_review_requires_complete_live_evidence(settings):
    snap=healthy(settings)
    assert rules.review({'flood.max':'32'},settings,snap,KEY)['confidence']=='limited local observations'
    for field,value in [('running',False),('heartbeat',0),('dropped',1),('trimmed_at',1),('radio','Offline'),('error','broken')]:
        data=copy.deepcopy(snap);data['health'][field]=value
        assert rules.review({},settings,data,KEY)['evidence_reasons']
    snap['usefulness']['partial']=True
    assert rules.review({},settings,snap,KEY)['confidence']=='insufficient observations'


def test_wrong_identity_and_period(settings):
    snap=healthy(settings);snap['days']=1
    result=rules.review({},settings,snap,'cd'*32)
    assert len(result['evidence_reasons'])==2
    assert not any(r['can_apply'] for r in result['rows'])


def control():
    c=RepeaterControl(NS(mc=NS(commands=NS())))
    c.transport=NS(contact=AsyncMock(return_value={'public_key':KEY,'type':2}),login=AsyncMock(return_value={'is_admin':True}),cli=AsyncMock())
    return c


def test_apply_and_restore_are_verified_and_recorded(tmp_path,monkeypatch):
    monkeypatch.setattr(history,'FILE',tmp_path/'history.db')
    c=control();c.transport.cli.side_effect=['> 32','> 32','OK','> 16','> 16','> 16','OK','> 32']
    async def scenario():
        login=await c.execute(dict(action='login',public_key=KEY))
        base=dict(public_key=KEY,session=login['session'],field='flood.max')
        for before,after in [('32','16'),('16','32')]:
            await c.execute(dict(base,action='read'))
            result=await c.execute(dict(base,action='advisor_write',expected=before,value=after,confirm=True))
            assert result['value']==after
    asyncio.run(scenario())
    rows=history.recent(KEY)
    assert len(rows)==2 and all(r['status']=='verified' for r in rows)
    assert rows[0]['before_value']=='16' and rows[0]['actual']=='32'
    assert history.recent('cd'*32)==[]


@pytest.mark.parametrize('outcome',[asyncio.TimeoutError(), '> 8'])
def test_uncertain_or_different_readback(tmp_path,monkeypatch,outcome):
    monkeypatch.setattr(history,'FILE',tmp_path/'history.db')
    c=control();c.transport.cli.side_effect=['> 32','> 32','OK',outcome]
    async def scenario():
        login=await c.execute(dict(action='login',public_key=KEY))
        base=dict(public_key=KEY,session=login['session'],field='flood.max')
        await c.execute(dict(base,action='read'))
        try: await c.execute(dict(base,action='advisor_write',expected='32',value='16',confirm=True))
        except ValueError: pass
    asyncio.run(scenario())
    assert history.recent(KEY)[0]['status']!='verified'
    assert c.transport.cli.await_count==4


def test_stale_value_prevents_write(tmp_path,monkeypatch):
    monkeypatch.setattr(history,'FILE',tmp_path/'history.db')
    c=control();c.transport.cli.side_effect=['> 32','> 8']
    async def scenario():
        login=await c.execute(dict(action='login',public_key=KEY))
        base=dict(public_key=KEY,session=login['session'],field='flood.max')
        await c.execute(dict(base,action='read'))
        with pytest.raises(ValueError,match='changed'):
            await c.execute(dict(base,action='advisor_write',expected='32',value='16',confirm=True))
    asyncio.run(scenario())
    assert c.transport.cli.await_count==2
    assert history.recent(KEY)==[]


def test_api_refreshes_requested_window_and_uses_shared_validation(tmp_path,monkeypatch,settings):
    monkeypatch.setattr(web,'FILE',tmp_path/'settings.json');monkeypatch.setattr(history,'FILE',tmp_path/'history.db')
    days=[]
    def snapshot(day):
        days.append(day);return {'days':day,'health':{},'selection':{'public_key':KEY}}
    monkeypatch.setattr(web,'snapshot',snapshot)
    app=Flask(__name__);web.register_advisor_routes(app);client=app.test_client();headers={'X-Meshcore-Control':'1'}
    assert client.get('/api/repeater-advisor').status_code==403
    assert client.get('/api/repeater-advisor?days=30',headers=headers).json['statistics']['days']==30
    settings['min_days']=1
    result=client.post('/api/repeater-advisor',json={'action':'review','settings':settings,'current':{'flood.max':'32'},'public_key':KEY},headers=headers)
    assert result.status_code==200 and days==[30,1]
    assert 'evaluations' in result.json
    assert not web.FILE.exists()
    settings['targets']['advert.interval']=2
    assert client.post('/api/repeater-advisor',json={'action':'save','settings':settings},headers=headers).status_code==400


def test_lightweight_snapshot_is_target_and_period_bound(tmp_path,monkeypatch):
    from meshcorestation.storage import passive_stats
    monkeypatch.setattr(passive_stats,'STATS_PATH',tmp_path/'stats.db')
    passive_stats.initialize()
    now=time.time()
    with passive_stats.connect() as db:
        db.execute('INSERT INTO selection VALUES(1,?,?)',(KEY,now-10*86400))
        for key,at,digest in [(KEY,now-60,'a'),(KEY,now-120,'a'),(KEY,now-2*86400,'b'),('cd'*32,now-60,'c'),(KEY,now+86400,'d')]:
            db.execute('INSERT INTO observations(target,at,digest,kind,scoped,ambiguous,first_hop,middle_hop,last_hop,route,previous,following) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (key,at,digest,4,0,0,1,0,0,'[{},{}]','[]','[]'))
    data=web.snapshot(1)
    assert data['copies']==2 and data['unique']==1
    assert data['evidence']['repeated']==1 and data['evidence']['max_hops']==2
    assert web.snapshot(7)['copies']==3


def test_references_never_become_statistical_recommendations(settings):
    snap=healthy(settings)
    report=rules.review({'flood.max':'32','loop.detect':'off'},settings,snap,KEY)
    assert report['rows'][0]['status']=='Differs from reference'
    assert not any(row['can_apply'] for row in report['rows'])
    assert not any(r['can_apply'] for r in report['recommendations'])


def test_statistics_drive_trials_and_preserve_conservative_gate(settings):
    snap=healthy(settings)
    snap['copies']=400
    snap['evidence']={'identified':300,'repeated':150,'routes':6,'active_days':7,
                      'unscoped':260,'adverts':160}
    current={'loop.detect':'off','flood.max':'32','flood.max.unscoped':'16'}
    report=rules.review(current,settings,snap,KEY)
    recommendations={r['id']:r for r in report['recommendations']}
    assert 'loop-trial' in recommendations
    trial=recommendations['loop-trial']
    assert trial['proposed']=='minimal' and trial['field']=='loop.detect'
    assert trial['can_apply'] and trial['confidence']=='experimental'
    assert 'unscoped' in recommendations and 'adverts' in recommendations
    assert not recommendations['unscoped']['can_apply']
    assert not recommendations['adverts']['can_apply']
    assert not any(row['can_apply'] for row in report['rows'])
    # Different real observations should produce different recommendations
    snap['evidence']={'identified':300,'repeated':5,'routes':6,'active_days':7,
                      'unscoped':10,'adverts':10}
    quieter=rules.review(current,settings,snap,KEY)
    assert not any(r['can_apply'] for r in quieter['recommendations'])
    assert not any(r['id']=='loop-trial' for r in quieter['recommendations'])


@pytest.mark.parametrize('change',[
    {'health':{'radio':'Offline'}},
    {'selection':{'public_key':'cd'*32,'since':0}},
    {'usefulness':{'partial':True}},
    {'evidence':{'identified':300,'repeated':150,'routes':6,'active_days':1,'unscoped':250,'adverts':200}},
    {'evidence':{'identified':300,'repeated':150,'routes':1,'active_days':7,'unscoped':250,'adverts':200}},
])
def test_incomplete_or_inconclusive_data_cannot_offer_loop_trial(settings,change):
    snap=healthy(settings)
    snap['copies']=400
    snap['evidence']={'identified':300,'repeated':150,'routes':6,'active_days':7,
                      'unscoped':250,'adverts':200}
    snap.update(change)
    result=rules.review({'loop.detect':'off'},settings,snap,KEY)
    assert not any(r['can_apply'] for r in result['recommendations'])


def test_snapshot_aggregates_activity_and_route_diversity(tmp_path,monkeypatch):
    from meshcorestation.storage import passive_stats
    monkeypatch.setattr(passive_stats,'STATS_PATH',tmp_path/'stats.db')
    passive_stats.initialize()
    now=time.time()
    with passive_stats.connect() as db:
        db.execute('INSERT INTO selection VALUES(1,?,?)',(KEY,now-9*86400))
        for days,route,digest in [(0,'[{},{}]','a'),(0,'[{},{}]','a'),
                                  (1,'[{},{}]','b'),(2,'[{}]','c')]:
            db.execute('INSERT INTO observations(target,at,digest,kind,scoped,ambiguous,first_hop,middle_hop,last_hop,route,previous,following) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (KEY,now-days*86400-600,digest,4,0,0,1,0,0,route,'[]','[]'))
    data=web.snapshot(7)
    assert data['evidence']['identified']==4
    assert data['evidence']['repeated']==1
    assert data['evidence']['routes']==2
    assert data['evidence']['active_days']>=2



def test_unidentified_payloads_do_not_trigger_trial(settings):
    snap=healthy(settings)
    snap['copies']=1000
    snap['evidence']={'identified':160,'repeated':120,'routes':5,
                      'active_days':7,'unscoped':550,'adverts':100}
    result=rules.review({'loop.detect':'off'},settings,snap,KEY)
    assert not any(r['can_apply'] for r in result['recommendations'])
