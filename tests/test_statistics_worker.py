"""Regression for fast CLI but timing-out HTTP threads in a busy interpreter."""
import json
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from unittest.mock import Mock
import pytest
from scripts.benchmark_statistics import create_fixture,KEY
from meshcorestation.storage import passive_stats
from meshcorestation.web import statistics_service as service


@pytest.fixture
def saved(tmp_path):
    path=create_fixture(tmp_path,2517)
    with sqlite3.connect(passive_stats.statistics_path(path,KEY)) as db:
        db.execute('UPDATE observations SET received_at=?',(time.time()-1,))
    service.open_worker_service()
    yield path
    service.close_worker()
    service.open_worker_service()


def test_isolated_view_succeeds_with_competing_python_thread(saved):
    stop=threading.Event();counter=[0]
    def busy():
        while not stop.is_set():counter[0]+=1
    thread=threading.Thread(target=busy);thread.start()
    try:
        result=service.saved_view(saved,KEY,1)
        assert result['ok'] and result['diagnostics']['source_rows']==2517
        assert counter[0]>0 and service.WORKER is None
        assert result['diagnostics']['stages_ms']['classify']<8000
    finally:stop.set();thread.join(timeout=2)


def test_child_does_not_import_or_open_radio_runtime(saved):
    script="""
import sys
from meshcorestation.web.statistics_worker import aggregate
value=aggregate(__import__('pathlib').Path(sys.argv[1]),sys.argv[2],1)
assert value['ok']
assert 'meshcorestation.runtime' not in sys.modules
assert 'meshcorestation.radio.companion' not in sys.modules
assert 'meshcore' not in sys.modules
print('read-only worker imports verified')
"""
    result=subprocess.run([sys.executable,'-c',script,str(saved),KEY],capture_output=True,text=True,timeout=9)
    assert result.returncode==0,result.stderr


def test_parent_timeout_reaps_worker_and_allows_later_request(saved,monkeypatch):
    # Force the parent deadline, not the unchanged 8s calculation deadline.
    monkeypatch.setattr(service,'WORKER_TIMEOUT_SECONDS',.001)
    with pytest.raises(service.QueryTimeout):service.aggregate(saved,KEY,1)
    assert service.WORKER is None
    monkeypatch.setattr(service,'WORKER_TIMEOUT_SECONDS',9)
    assert service.aggregate(saved,KEY,1)['ok']


def test_shutdown_reaps_running_child(saved,monkeypatch):
    real=service.subprocess.Popen;started=threading.Event();processes=[]
    def sleeping(*args,**kwargs):
        child=real([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
        processes.append(child);started.set();return child
    monkeypatch.setattr(service.subprocess,'Popen',sleeping)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task=pool.submit(service.aggregate,saved,KEY,1)
        assert started.wait(2);service.close_worker()
        with pytest.raises(service.StatisticsWorkerError):task.result(timeout=3)
    assert processes[0].poll() is not None and service.WORKER is None
    with pytest.raises(service.StatisticsWorkerError):service.aggregate(saved,KEY,1)


def test_worker_preserves_schema_and_raw_saved_history(saved):
    source=passive_stats.statistics_path(saved,KEY)
    with sqlite3.connect(source) as db:
        before=db.execute('SELECT COUNT(*),SUM(id),SUM(LENGTH(payload)) FROM observations').fetchone()
        schema=db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall()
    first=service.saved_view(saved,KEY,1);second=service.saved_view(saved,KEY,1)
    assert first['ok'] and second['cached']
    with sqlite3.connect(source) as db:
        assert db.execute('SELECT COUNT(*),SUM(id),SUM(LENGTH(payload)) FROM observations').fetchone()==before
        assert db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall()==schema


def test_child_database_error_is_reported_without_overwriting_history(saved):
    source=passive_stats.statistics_path(saved,KEY);source.write_bytes(b'synthetic damaged database')
    before=source.read_bytes()
    with pytest.raises(sqlite3.Error):service.aggregate(saved,KEY,1)
    assert source.read_bytes()==before and service.WORKER is None


def test_large_worker_periods_allow_concurrent_passive_recording(tmp_path):
    import asyncio
    from meshcorestation.radio.statistics_collector import Collector
    path=create_fixture(tmp_path,100000)
    with sqlite3.connect(passive_stats.statistics_path(path,KEY)) as db:db.execute('UPDATE observations SET received_at=?',(time.time()-1,))
    service.open_worker_service()
    async def run():
        collector=Collector(path,Mock(),batch_size=4,interval=.001);collector.start()
        task=asyncio.create_task(asyncio.to_thread(service.aggregate,path,KEY,1))
        try:
            for _ in range(200):
                if service.WORKER is not None:break
                await asyncio.sleep(.005)
            assert service.WORKER is not None
            for i in range(16):
                collector.submit(dict(route_type=1,payload_type=5,path='aa11',path_len=1,path_hash_size=2,pkt_payload=f'worker concurrent {i}'.encode()))
                await asyncio.sleep(.002)
            await collector.queue.join()
            assert not collector.error and not collector.errors and collector.dropped==0
            assert not task.done(),'worker must still be reading while passive writes commit'
            result=await task;assert result['diagnostics']['source_rows']>=100000
        finally:await collector.close();await task
    try:
        asyncio.run(run())
        for days in (7,30):assert service.aggregate(path,KEY,days)['diagnostics']['source_rows']==100016
        with sqlite3.connect(passive_stats.statistics_path(path,KEY)) as db:assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==100016
    finally:service.close_worker();service.open_worker_service()
