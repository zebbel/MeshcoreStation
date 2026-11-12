"""Required scale matrix and isolation checks; synthetic data, never RF."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import logging
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from flask import Flask
from scripts.benchmark_statistics import create_fixture,KEY,NOW
from meshcorestation.storage import statistics_view as view,passive_stats
from meshcorestation.web import statistics_service as service


@pytest.fixture(params=[2500,10000,50000,100000])
def workload(tmp_path,request):
    return create_fixture(tmp_path,request.param),request.param


def test_required_sizes_all_periods_bounded_and_same_observations(workload):
    path,count=workload
    source=passive_stats.statistics_path(path,KEY)
    with sqlite3.connect(source) as db:
        before=db.execute('SELECT COUNT(*),SUM(id),MAX(recorded_at) FROM observations').fetchone()
        plan=db.execute('EXPLAIN QUERY PLAN SELECT id FROM observations WHERE received_at>=? AND received_at<?',(NOW-86400,NOW)).fetchall()
    assert any('observations_timestamp' in row[3] and 'SEARCH' in row[3] for row in plan)
    total=None
    for days in (1,7,30):
        result=view.aggregate(path,KEY,days,now=NOW)
        assert result['diagnostics']['source_rows']==count
        assert result['diagnostics']['route_cache_bytes']<=8*1024*1024
        assert result['diagnostics']['parsed_routes']<=512
        assert result['totals']['receptions']>0 and result['neighbors']
        assert 'Unscoped' in {r['name'] for r in result['regions']}
        if total is None:total=result['totals']
        else:assert result['totals']==total
    with sqlite3.connect(source) as db:assert db.execute('SELECT COUNT(*),SUM(id),MAX(recorded_at) FROM observations').fetchone()==before


def test_2292_rows_load_and_diagnostics_never_log_packet_contents(tmp_path,caplog):
    path=create_fixture(tmp_path,2292)
    with caplog.at_level(logging.DEBUG,logger='meshcorestation.statistics'):
        result=view.aggregate(path,KEY,1,now=NOW)
    assert result['diagnostics']['source_rows']==2292
    assert {'classify','hourly','hops','regions','neighbors','coverage'}<=result['diagnostics']['stages_ms'].keys()
    assert 'stage=neighbors' in caplog.text and 'rows=2292' in caplog.text
    assert 'Synthetic ' not in caplog.text and 'aa11' not in caplog.text
    assert 'payload' not in caplog.text


def test_cache_reuses_work_but_invalidates_on_new_saved_observation(tmp_path,monkeypatch):
    path=create_fixture(tmp_path,2500);calls=[]
    real=view.aggregate
    def counted(*args):calls.append(1);return real(*args,now=NOW)
    monkeypatch.setattr(service,'aggregate',counted)
    with service.LOCK:service.CACHE.clear()
    first=service.saved_view(path,KEY,1)
    for _ in range(5):assert service.saved_view(path,KEY,1)['cached'] is True
    assert len(calls)==1 and not first['cached']
    packet=passive_stats.normalize(dict(route_type=1,payload_type=5,path='aa11',path_len=1,path_hash_size=2,pkt_payload=b'new saved fixture'),now_ns=int((NOW-1)*1e9))
    passive_stats.store_batch(path,[packet])
    second=service.saved_view(path,KEY,1)
    assert len(calls)==2 and not second['cached']
    assert second['totals']['receptions']==first['totals']['receptions']+1
    with sqlite3.connect(path) as db:db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(KEY,))
    with pytest.raises(ValueError):service.saved_view(path,KEY,1)
    assert len(service.CACHE)<=2


def test_concurrent_expensive_requests_fail_fast_while_status_remains_available(tmp_path,monkeypatch):
    from meshcorestation import config
    from meshcorestation.web.statistics_api import register_statistics_routes
    path=create_fixture(tmp_path,2500);monkeypatch.setattr(config,'DB_PATH',path)
    entered,release=threading.Event(),threading.Event()
    def blocked(*args):entered.set();assert release.wait(5);return dict(ok=True)
    monkeypatch.setattr(service,'aggregate',blocked)
    with service.LOCK:service.CACHE.clear()
    app=Flask(__name__);register_statistics_routes(app)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task=pool.submit(service.saved_view,path,KEY,1)
        try:
            assert entered.wait(2)
            client=app.test_client()
            assert client.get('/api/repeater-statistics/status').status_code==200
            response=client.get('/api/repeater-statistics/view?public_key='+KEY)
            assert response.status_code==429 and response.json['error_code']=='STATISTICS_BUSY'
        finally:release.set();task.result(timeout=5)


def test_passive_recording_commits_during_large_view_read(tmp_path,monkeypatch):
    from meshcorestation.radio.statistics_collector import Collector
    path=create_fixture(tmp_path,100000)
    entered,finished=threading.Event(),threading.Event();committed=[]
    real_spool=view._spool;real_write=passive_stats._write
    def spool(*args):entered.set();return real_spool(*args)
    def write(*args):real_write(*args);committed.append(not finished.is_set())
    monkeypatch.setattr(view,'_spool',spool);monkeypatch.setattr(passive_stats,'_write',write)
    def calculate():
        try:return view.aggregate(path,KEY,1,now=NOW)
        finally:finished.set()
    async def run():
        collector=Collector(path,Mock(),capacity=64,batch_size=4,interval=.001);collector.start()
        task=asyncio.create_task(asyncio.to_thread(calculate))
        try:
            assert await asyncio.to_thread(entered.wait,3)
            for i in range(16):
                collector.submit(dict(route_type=1,payload_type=5,path='aa11',path_len=1,path_hash_size=2,pkt_payload=f'concurrent fixture {i}'.encode()))
                await asyncio.sleep(.002)
            await collector.queue.join()
            assert not collector.error and not collector.errors and collector.dropped==0
            result=await task;assert result['totals']['receptions']>0
        finally:
            await collector.close();await task
    asyncio.run(run())
    assert any(committed),'at least one actual WAL write must commit before aggregation completes'
    with sqlite3.connect(passive_stats.statistics_path(path,KEY)) as db:assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==100016


def test_timeout_and_database_errors_have_distinct_http_codes(tmp_path,monkeypatch):
    from meshcorestation import config
    from meshcorestation.web.statistics_api import register_statistics_routes
    path=create_fixture(tmp_path,2500);monkeypatch.setattr(config,'DB_PATH',path)
    app=Flask(__name__);register_statistics_routes(app);client=app.test_client()
    def timeout(*a):raise view.QueryTimeout('neighbors')
    monkeypatch.setattr(service,'saved_view',timeout)
    response=client.get('/api/repeater-statistics/view')
    assert response.status_code==504 and response.json['error_code']=='QUERY_TIMEOUT' and response.json['stage']=='neighbors'
    def busy(*a):
        error=sqlite3.OperationalError('locked');error.sqlite_errorcode=sqlite3.SQLITE_BUSY;raise error
    monkeypatch.setattr(service,'saved_view',busy)
    assert client.get('/api/repeater-statistics/view').json['error_code']=='DATABASE_BUSY'
    def damaged(*a):raise sqlite3.DatabaseError('bad database')
    monkeypatch.setattr(service,'saved_view',damaged)
    assert client.get('/api/repeater-statistics/view').json['error_code']=='DATABASE_ERROR'
    assert client.get('/api/repeater-statistics/status').status_code==200
    monkeypatch.setattr(view,'QUERY_BUDGET_SECONDS',0)
    with pytest.raises(view.QueryTimeout):view.aggregate(path,KEY,1,now=NOW)


def test_scratch_space_cannot_consume_recording_reserve(tmp_path,monkeypatch):
    path=create_fixture(tmp_path,2500)
    monkeypatch.setattr(view.shutil,'disk_usage',lambda _:NS(free=passive_stats.MIN_FREE_BYTES+1))
    with pytest.raises(OSError,match='reserve'):view.aggregate(path,KEY,1,now=NOW)
    with sqlite3.connect(passive_stats.statistics_path(path,KEY)) as db:assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==2500


def test_classifications_reuse_overlap_and_track_data_and_configuration(tmp_path):
    path = create_fixture(tmp_path, 2500)
    source = passive_stats.statistics_path(path, KEY)

    def compare(days, now=NOW):
        reused = view.aggregate(path, KEY, days, now=now)
        independent = view.aggregate(path, KEY, days, now=now, _reuse=False)
        assert {k: v for k, v in reused.items() if k != 'diagnostics'} == {
            k: v for k, v in independent.items() if k != 'diagnostics'}
        return reused['diagnostics']['classified_rows']

    assert compare(7) == 2500
    assert compare(1) == 0
    assert compare(30) == 0
    packet = passive_stats.normalize(dict(route_type=1, payload_type=5, path='aa11',
        path_len=1, path_hash_size=2, pkt_payload=b'new or repeated'), now_ns=int((NOW - 1)*1e9))
    passive_stats.store_batch(path, [packet])
    assert compare(1, NOW + 1) == 1
    assert compare(7, NOW + 1) == 0

    # Registry metadata is rendered live. A key collision invalidates all facts.
    with sqlite3.connect(path.with_name('knownRepeaters.db')) as db:
        db.execute("UPDATE repeaters SET name='Renamed' WHERE public_key=?", (KEY,))
    assert compare(7, NOW + 1) == 0
    with sqlite3.connect(path.with_name('knownRepeaters.db')) as db:
        db.execute("""INSERT INTO repeaters(public_key,name,first_seen,source) VALUES(?,?,0,'contact')""",
                   ('aa11' + 'bb' * 30, 'Collision'))
    assert compare(7, NOW + 1) == 2501

    with sqlite3.connect(path) as db:
        db.execute("UPDATE statistics_regions SET name='renamed' WHERE name='region-1'")
    assert compare(7, NOW + 1) == 2501
    with sqlite3.connect(source) as db:
        db.execute('UPDATE observations SET ambiguous=1 WHERE id=1')
        db.execute('DELETE FROM observations WHERE id=2')
    assert compare(7, NOW + 1) == 2500


def test_readonly_legacy_history_and_unavailable_cache_fall_back(tmp_path):
    path = create_fixture(tmp_path, 2500)
    source = passive_stats.statistics_path(path, KEY)
    with sqlite3.connect(source) as db:
        for action in ('insert', 'update', 'delete'):
            db.execute(f'DROP TRIGGER classification_{action}')
        db.execute('DROP TABLE classification_source')
    assert view.aggregate(path, KEY, 7, now=NOW)['diagnostics']['classified_rows'] == 2500
    cache = tmp_path / 'statistics-classification.sqlite'
    assert not cache.exists()
    packet = passive_stats.normalize(dict(route_type=1, payload_type=5, path='aa11',
        path_len=1, path_hash_size=2, pkt_payload=b'first post-update'), now_ns=int((NOW - 1)*1e9))
    passive_stats.store_batch(path, [packet])
    cache.mkdir()
    assert view.aggregate(path, KEY, 7, now=NOW)['diagnostics']['classified_rows'] == 2501


def test_interrupted_classification_resumes_without_returning_partial_counts(tmp_path):
    path = create_fixture(tmp_path, 2500)
    with pytest.raises(view.QueryTimeout, match='classify') as timed_out:
        view.aggregate(path, KEY, 7, now=NOW, _budget=.7)
    assert timed_out.value.diagnostics['classification_progress_saved']
    assert 0 < timed_out.value.diagnostics['classified_rows'] < 2500
    resumed = view.aggregate(path, KEY, 7, now=NOW + 1)
    complete = view.aggregate(path, KEY, 7, now=NOW + 1, _reuse=False)
    assert resumed['diagnostics']['classified_rows'] < 2500
    assert {k: v for k, v in resumed.items() if k != 'diagnostics'} == {
        k: v for k, v in complete.items() if k != 'diagnostics'}
