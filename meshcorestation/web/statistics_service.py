"""Bound concurrent view work; recording/status never acquire this semaphore."""
from collections import OrderedDict
import json
from pathlib import Path
import threading
import time
from meshcorestation.storage import passive_stats
from meshcorestation.storage.statistics_view import aggregate

SLOT=threading.BoundedSemaphore(1)
LOCK=threading.Lock()
CACHE=OrderedDict()
CACHE_SECONDS=2.0


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
