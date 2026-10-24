"""Unattended multi-day runs use a simulated clock and captured response shapes."""
import copy
import json
import sqlite3
from datetime import datetime, timezone
import pytest
from test_performance import KEY, OTHER, DATA, stores, p, packet
from test_analyzer import NAMES, BODIES
from meshcorestation.analyzer import AnalyzerService, ENDPOINTS
from meshcorestation.analyzer_collector import AnalyzerCollector, INTERVAL, SPACING, LEASE

NOW=1792922400.0 # Fixed UTC hour; never reads live API or radio.


def data_at(now, missing=(), count=3):
    data=copy.deepcopy(DATA)
    end=int(now//3600)*3600
    data['detail']['relayTimeline']=[{'bucket':datetime.fromtimestamp(h,timezone.utc).isoformat(),'count':count}
        for h in range(end-24*3600,end,3600) if h not in missing]
    return data


def client(path,clock,calls,status=None):
    def fetch(url,headers,timeout):
        name=next(k for k in NAMES if ENDPOINTS[k].format(key=KEY) in url)
        calls.append((clock[0],name))
        if status and status[0]!=200:return status[0],{'Retry-After':'100000'},b''
        if name=='detail':return 200,{},json.dumps(data_at(clock[0])['detail']).encode()
        return 200,{},BODIES[name]
    return AnalyzerService(path/'cache.db',fetch,lambda:clock[0])


def test_60_hours_unattended_restart_hourly_dedup_and_cache(stores):
    clock=[NOW];calls=[];service=client(stores,clock,calls)
    worker=AnalyzerCollector(service,lambda:[KEY],lambda:clock[0])
    assert worker.tick();assert len(calls)==8
    # Dashboard reads use the shared cache, not another set of HTTP calls.
    assert service.snapshot(KEY)['state']=='cached';assert len(calls)==8
    assert not worker.tick()
    for hour in range(1,61):
        clock[0]=NOW+hour*3600
        # Real process restart: recreate both service (including locks) and worker.
        if hour in (5,17,37):
            service=client(stores,clock,calls);worker=AnalyzerCollector(service,lambda:[KEY],lambda:clock[0])
        assert worker.tick()==(hour%12==0)
    assert len(calls)==6*8
    rows=p.hourly(KEY,NOW-24*3600,clock[0])
    assert len(rows)==84 and sum(r['count'] for r in rows)==84*3
    assert len({r['at'] for r in rows})==84
    assert p.collection_status(KEY)['next_at']==clock[0]+INTERVAL
    overview=p.overview(KEY,1,clock[0]);summary=overview['summary']
    assert summary['hourly_observed']==summary['hourly_expected']==24
    assert summary['trend_complete'] and 'unchanged' in summary['trend']
    assert overview['summary']['details']['pairs']==21
    assert overview['summary']['details']['betweenness']==DATA['metrics']['betweenness']
    assert all(r['hourly_relays']==3 for r in overview['hourly_timeline'])


def test_hourly_timestamps_corrections_invalid_current_and_missing(stores):
    data=data_at(NOW,missing=(int(NOW)-3600,))
    data['detail']['relayTimeline'] += [
        {'bucket':datetime.fromtimestamp(NOW,timezone.utc).isoformat(),'count':999}, # ongoing
        {'bucket':'2026-10-25T12:00:00','count':3}, # no timezone
        {'bucket':'bad','count':3}, {'bucket':None,'count':3},
        {'bucket':datetime.fromtimestamp(NOW-3600,timezone.utc).isoformat(),'count':False},
        {'bucket':datetime.fromtimestamp(NOW-1800,timezone.utc).isoformat(),'count':3}]
    p.record_analyzer(KEY,NOW,data)
    assert len(p.hourly(KEY,NOW-86400,NOW))==23
    revised=data_at(NOW,count=7)
    p.record_analyzer(KEY,NOW+1,revised)
    rows=p.hourly(KEY,NOW-86400,NOW)
    assert len(rows)==24 and all(r['count']==7 and r['retrieved_at']==NOW+1 for r in rows)
    p.record_analyzer(KEY,NOW,data) # stale cache cannot overwrite correction
    assert all(r['count']==7 for r in p.hourly(KEY,NOW-86400,NOW))
    result=p.overview(KEY,1,NOW)
    assert result['summary']['hourly_total']==168
    p.record_analyzer(KEY,NOW+p.RETENTION+1,data_at(NOW+p.RETENTION+1))
    assert not p.hourly(KEY,NOW-86400,NOW)
    assert p.overview(KEY,1,NOW+p.RETENTION+2)['summary']['hourly_total'] is not None


def test_missing_hour_withholds_trend_and_is_chart_gap(stores):
    p.record_analyzer(KEY,NOW,data_at(NOW,missing=(int(NOW)-4*3600,)))
    result=p.overview(KEY,1,NOW)
    assert not result['summary']['trend_complete']
    assert result['summary']['trend_percent'] is None
    assert result['summary']['hourly_observed']==23
    assert any(r['hourly_relays'] is None for r in result['hourly_timeline'])
    # An explicit zero is preserved and is different from a missing hour.
    zero=data_at(NOW,count=0);p.record_analyzer(KEY,NOW+1,zero)
    assert p.overview(KEY,1,NOW+1)['summary']['hourly_total']==0


@pytest.mark.parametrize('status',[403,429,500])
def test_failures_survive_restart_and_do_not_zero_or_retry_burst(stores,status):
    clock=[NOW];calls=[];http=[200]
    service=client(stores,clock,calls,http);worker=AnalyzerCollector(service,lambda:[KEY],lambda:clock[0])
    assert worker.tick();saved=p.hourly(KEY,NOW-86400,NOW)
    clock[0]+=INTERVAL;http[0]=status;assert worker.tick()
    state=p.collection_status(KEY);assert state['error'] and state['success_at']==NOW
    assert p.hourly(KEY,NOW-86400,NOW)==saved
    count=len(calls)
    service=client(stores,clock,calls,http);worker=AnalyzerCollector(service,lambda:[KEY],lambda:clock[0])
    for delta in (1,60,600,3600):clock[0]=NOW+INTERVAL+delta;assert not worker.tick()
    assert len(calls)==count
    if status==429:
        clock[0]=NOW+2*INTERVAL;assert not worker.tick() # Retry-After > 12h persisted globally
    else:
        clock[0]=NOW+2*INTERVAL;http[0]=200;assert worker.tick()


def test_global_spacing_claim_lease_crash_and_removed_repeaters(stores):
    clock=[NOW];calls=[];keys=[KEY,OTHER]
    service=client(stores,clock,calls)
    # Only KEY can be fetched using captured IDs; the other is deliberately unavailable.
    original=service.snapshot
    service.snapshot=lambda key,**kw: original(key,**kw) if key==KEY else {'state':'unavailable','error':'Offline','data':None}
    worker=AnalyzerCollector(service,lambda:keys,lambda:clock[0])
    assert worker.tick();assert not worker.tick()
    clock[0]+=SPACING;assert worker.tick()
    # Simulate process death after its durable claim: wait for lease before retry.
    with p.database() as db:
        db.execute("UPDATE collection_schedule SET next_at=?,state='collecting' WHERE public_key=?",(clock[0]+LEASE,KEY))
    clock[0]+=SPACING;assert not worker.tick()
    clock[0]+=LEASE;assert worker.tick()
    keys.remove(KEY);service.remove(KEY)
    clock[0]+=INTERVAL
    worker.tick();assert p.collection_status(KEY) is None
    assert not p.hourly(KEY,0,clock[0])


def test_hourly_before_after_exact_windows_not_rolling_sums(stores):
    marker_at=NOW-86400
    p.record_analyzer(KEY,marker_at,data_at(marker_at,count=2))
    p.record_analyzer(KEY,NOW,data_at(NOW,count=4))
    # Deliberately huge rolling counts must not replace the original hourly data.
    marker={'id':1,'at':marker_at}
    result=p.comparison(KEY,marker,1,NOW,[])
    assert result['windows']['before']['analyzer_samples']==24
    assert result['windows']['after']['analyzer_samples']==24
    assert result['differences']['analyzer_hourly_relays_mean']['before']==2
    assert result['differences']['analyzer_hourly_relays_mean']['after']==4
    assert result['differences']['analyzer_hourly_relays_mean']['percent']==100
    assert result['windows']['before']['analyzer_source']=='Original hourly buckets'


def test_collector_thread_start_close_is_idempotent(stores):
    import threading
    worker=AnalyzerCollector(client(stores,[NOW],[]),lambda:[],lambda:NOW)
    entered=threading.Event()
    worker.tick=lambda:entered.set()
    worker.start();assert entered.wait(1);thread=worker.thread
    worker.start();assert worker.thread is thread
    worker.close();assert not thread.is_alive()


def test_provider_retry_after_is_preserved_for_manual_reads_after_restart(stores):
    clock=[NOW];calls=[];http=[429]
    service=client(stores,clock,calls,http)
    assert service.snapshot(KEY)['state']=='rate_limited'
    assert service.blocked_until==NOW+100000
    restarted=client(stores,clock,calls,http)
    clock[0]+=50000
    assert restarted.snapshot(KEY,force=True)['state']=='rate_limited'
    assert len(calls)==1
    clock[0]+=50001;http[0]=200
    assert restarted.snapshot(KEY)['state']=='available'


@pytest.mark.parametrize('failure',['timeout','malformed'])
def test_collector_transport_and_validation_failures_remain_unknown(stores,failure):
    clock=[NOW];service=client(stores,clock,[])
    def fetch(*args):
        if failure=='timeout':raise TimeoutError()
        return 200,{},b'not JSON'
    service.fetch=fetch
    worker=AnalyzerCollector(service,lambda:[KEY],lambda:clock[0])
    assert worker.tick()
    assert p.hourly(KEY,0,NOW)==[]
    state=p.collection_status(KEY)
    assert state['success_at'] is None and state['error'] and state['next_at']==NOW+INTERVAL
    result=p.overview(KEY,7,NOW)
    assert not result['summary']['trend_complete'] and result['summary']['hourly_total'] is None


def test_retention_caps_all_measurement_tables_but_not_journal(stores,monkeypatch):
    monkeypatch.setattr(p,'MAX_SAMPLES',2)
    p.marker_change(KEY,'create',{'description':'Permanent journal','at':100},now=NOW)
    for i in range(4):p.record_analyzer(KEY,NOW+i,data_at(NOW+i))
    with p.database() as db:
        for table in ('measurements','measurement_details','hourly_relays'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==2
    assert len(p.markers(KEY))==1


def test_busy_client_defers_without_losing_the_twelve_hour_collection(stores):
    clock=[NOW];calls=[];service=client(stores,clock,calls)
    worker=AnalyzerCollector(service,lambda:[KEY],lambda:clock[0])
    service.lock.acquire()
    try:
        assert worker.tick()
        assert p.collection_status(KEY)['next_at']==NOW+SPACING
        assert not calls
    finally:
        service.lock.release()
    clock[0]+=SPACING
    assert worker.tick() and len(calls)==8
    assert p.collection_status(KEY)['success_at']==clock[0]


def test_offset_hour_dedup_and_non_aligned_change_windows(stores):
    from datetime import timedelta
    at=NOW-86400
    p.record_analyzer(KEY,at,data_at(at,count=2))
    p.record_analyzer(KEY,NOW,data_at(NOW,count=4))
    correction=data_at(NOW,count=6)
    for row in correction['detail']['relayTimeline']:
        row['bucket']=datetime.fromisoformat(row['bucket']).astimezone(timezone(timedelta(hours=2))).isoformat()
    p.record_analyzer(KEY,NOW+1,correction)
    assert len(p.hourly(KEY,NOW-86400,NOW))==24
    assert all(r['count']==6 for r in p.hourly(KEY,NOW-86400,NOW))
    result=p.comparison(KEY,{'id':1,'at':at+300},1,NOW+300,[])
    assert result['windows']['before']['expected_hourly_samples']==23
    assert result['windows']['after']['expected_hourly_samples']==23
    assert result['differences']['analyzer_hourly_relays_mean']['percent']==200


def test_reach_snapshot_at_change_belongs_only_to_after(stores):
    p.record_analyzer(KEY,NOW,data_at(NOW))
    result=p.comparison(KEY,{'id':1,'at':NOW},1,NOW+86400,[])
    assert result['windows']['before']['values']['analyzer_neighbors_mean'] is None
    assert result['windows']['before']['analyzer_snapshot_samples']==0
    assert result['windows']['after']['values']['analyzer_neighbors_mean'] is not None
    assert result['windows']['after']['analyzer_snapshot_samples']==1


def test_only_managed_valid_keys_are_collected(stores,monkeypatch):
    import meshcorestation.analyzer_collector as module
    path=stores/'station.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE voltage_config (id INTEGER, public_key TEXT, managed INTEGER)')
        db.executemany('INSERT INTO voltage_config VALUES(?,?,?)',[(1,KEY.upper(),1),(2,OTHER,0),(3,'',1),(4,'invalid legacy ID',1)])
    monkeypatch.setattr(module,'DB_PATH',path)
    assert module.managed_keys()==[KEY]


def test_block_pauses_other_managed_repeaters_and_survives_worker_restart(stores):
    clock=[NOW];calls=[];service=client(stores,clock,calls,[403])
    worker=AnalyzerCollector(service,lambda:[KEY,OTHER],lambda:clock[0])
    assert worker.tick() and len(calls)==1
    clock[0]+=SPACING
    restarted=AnalyzerCollector(client(stores,clock,calls,[403]),lambda:[KEY,OTHER],lambda:clock[0])
    assert not restarted.tick() and len(calls)==1
    assert p.collection_status(OTHER)['attempted_at'] is None
