"""Bound concurrent view work; recording/status never acquire this semaphore."""
from collections import OrderedDict
import json
from pathlib import Path
import threading
import subprocess
import sys
import logging
import sqlite3
import time
from meshcorestation.storage import passive_stats
from meshcorestation.storage.statistics_view import QueryTimeout

SLOT=threading.BoundedSemaphore(1)
LOCK=threading.Lock()
CACHE=OrderedDict()
CACHE_SECONDS=2.0
WORKER_TIMEOUT_SECONDS=9.0
WORKER_LOCK=threading.Lock()
WORKER=None
CLOSING=False
LOGGER=logging.getLogger('meshcorestation.statistics')


class StatisticsWorkerError(RuntimeError):pass


def close_worker():
    """Called by WebServer shutdown; no child retains radio/HTTP descriptors."""
    global CLOSING
    with WORKER_LOCK:
        CLOSING=True
        process=WORKER
    if process and process.poll() is None:
        try:process.terminate()
        except ProcessLookupError:return
        try:process.wait(timeout=1)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=1)


def open_worker_service():
    global CLOSING
    with WORKER_LOCK:CLOSING=False


def aggregate(main_path,key,days):
    """Fresh exec avoids sharing the radio interpreter's GIL or SQLite handles.

    Keep the existing 8s calculation budget. The parent has a 9s bound including
    worker startup/IPC, below the independent 10s browser saved-view deadline.
    """
    global WORKER
    started=time.monotonic()
    with WORKER_LOCK:
        if CLOSING:raise StatisticsWorkerError('Statistics service is stopping.')
        process=subprocess.Popen([sys.executable,'-m','meshcorestation.web.statistics_worker',str(main_path),key,str(days)],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True)
        WORKER=process
    try:
        try:output,diagnostics=process.communicate(timeout=WORKER_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill();process.communicate()
            raise QueryTimeout('worker execution') from None
        if process.returncode!=0:raise StatisticsWorkerError('Statistics worker stopped before returning a result.')
        if len(output)>8*1024*1024:raise StatisticsWorkerError('Statistics result exceeded the response limit.')
        try:value=json.loads(output)
        except (ValueError,UnicodeError):raise StatisticsWorkerError('Statistics worker returned an unreadable result.') from None
        if not isinstance(value,dict):raise StatisticsWorkerError('Statistics worker returned an invalid result.')
        code=value.get('error_code')
        if code=='QUERY_TIMEOUT':
            LOGGER.warning('Statistics worker timeout stage=%s diagnostics=%s',value.get('stage'),value.get('diagnostics',{}))
            raise QueryTimeout(value.get('stage','worker execution'),value.get('diagnostics',{}))
        if code=='SQLITE_ERROR':
            error=sqlite3.OperationalError('Saved statistics database could not be read.')
            error.sqlite_errorcode=value.get('sqlite_code');raise error
        if code=='STORAGE_ERROR':raise OSError('Statistics scratch storage unavailable.')
        if code=='INVALID_SELECTION':raise ValueError('Select a managed repeater.')
        if not value.get('ok'):raise StatisticsWorkerError('Statistics worker could not return a bounded result.')
        # Forward only controlled numeric diagnostics, never arbitrary child stderr.
        info=value.setdefault('diagnostics',{})
        info['worker_roundtrip_ms']=round((time.monotonic()-started)*1000,3)
        LOGGER.info('Statistics worker complete rows=%s stages_ms=%s',info.get('source_rows'),info.get('stages_ms'))
        return value
    finally:
        if process.poll() is None:process.kill();process.communicate()
        with WORKER_LOCK:
            if WORKER is process:WORKER=None



class StatisticsBusy(RuntimeError):pass


def _token(main_path,key):
    paths=[Path(main_path),Path(main_path).with_name('knownRepeaters.db')]
    if key:paths.append(passive_stats.statistics_path(main_path,key))
    values=[]
    for path in paths:
        for item in (path,Path(str(path)+'-wal')):
            try:
                stat=item.stat()
                # SQLite may chmod an existing WAL on read-open (ctime only),
                # or create an empty WAL. Neither changes committed observations.
                values.append(None if str(item).endswith('-wal') and stat.st_size==0 else (stat.st_ino,stat.st_size,stat.st_mtime_ns))
            except FileNotFoundError:values.append(None)
    return tuple(values)


def saved_view(main_path,key,days):
    # Cheap managed-list/status preflight also keeps cache hits managed-only.
    key=passive_stats.snapshot(main_path,key)['selected']
    token=_token(main_path,key);cache_key=(str(main_path),key,days)
    with LOCK:
        entry=CACHE.get(cache_key)
        if entry and entry[0]>time.monotonic() and entry[1]==token:
            CACHE.move_to_end(cache_key);return dict(entry[2],cached=True)
    if not SLOT.acquire(blocking=False):raise StatisticsBusy('Another saved statistics view is being calculated. Refresh after it finishes; recording status remains available.')
    try:
        value=aggregate(main_path,key,days)
        # Cap both entries and serialized size. No persistent cache/schema migration.
        if len(json.dumps(value).encode())<=4*1024*1024:
            with LOCK:
                CACHE[cache_key]=(time.monotonic()+CACHE_SECONDS,token,value)
                CACHE.move_to_end(cache_key)
                while len(CACHE)>2:CACHE.popitem(last=False)
        return dict(value,cached=False)
    finally:SLOT.release()
