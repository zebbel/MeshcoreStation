"""Low-frequency, unattended HTTPS collection. Never opens a radio session.

A persistent lease avoids startup bursts and duplicate workers; missed runs are
coalesced, not replayed. The dashboard retains its independent five-minute cache.
"""
from contextlib import closing
import logging
import sqlite3
import threading
import time
from meshcorestation.config import DB_PATH
from meshcorestation.analyzer import service, public_key
from meshcorestation.storage import performance_store as store

INTERVAL = 12 * 3600
SPACING = 60
LEASE = 1800


def managed_keys():
    # The main process initializes this database before starting the collector.
    with closing(sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True, timeout=5)) as db:
        keys=[]
        for row in db.execute("SELECT public_key FROM voltage_config WHERE managed=1 AND public_key!='' ORDER BY id"):
            try: keys.append(public_key(row[0]))
            except ValueError: logging.getLogger(__name__).warning('Skipping invalid managed repeater identifier')
        return keys


class AnalyzerCollector:
    def __init__(self, analyzer=service, keys=managed_keys, clock=time.time):
        self.analyzer, self.keys, self.clock = analyzer, keys, clock
        self.stop_event = threading.Event()
        self.thread = None

    def tick(self):
        """Run at most one due repeater. Injectable clock permits multi-day tests."""
        now=self.clock()
        keys=set(self.keys())
        path=self.analyzer.history_path
        with store.database(path) as db:
            # Obtain the SQLite writer lock before reading scheduling state.
            db.execute('UPDATE collection_control SET next_at=next_at WHERE id=1')
            gate=db.execute('SELECT next_at FROM collection_control WHERE id=1').fetchone()[0]
            if gate>now:
                return False
            for key in keys:
                state=store.lifecycle(db,key)
                if not state['deleted']:
                    db.execute('INSERT OR IGNORE INTO collection_schedule(public_key) VALUES(?)',(key,))
            due=[dict(r) for r in db.execute('SELECT * FROM collection_schedule WHERE next_at<=? ORDER BY next_at,public_key',(now,)) if r['public_key'] in keys]
            if not due:
                return False
            key=due[0]['public_key']
            revision=self.analyzer.revisions.get(key,0)
            db.execute("UPDATE collection_schedule SET next_at=?,attempted_at=?,state='collecting',error=NULL WHERE public_key=?",(now+LEASE,now,key))
            db.execute('UPDATE collection_control SET next_at=? WHERE id=1',(now+SPACING,))
        if key not in set(self.keys()):
            return False
        try:
            result=self.analyzer.snapshot(key, expected_revision=revision)
            success=result.get('data') is not None and not result.get('error') and not result.get('history_error')
            error=result.get('error') or result.get('history_error')
            if success:
                # Also retries a previous failed history write from a fresh cache.
                store.record_analyzer(key,result['fetched_at'],result['data'],path)
        except Exception:
            logging.getLogger(__name__).exception('Scheduled Analyzer collection failed')
            success=False;error='Scheduled Analyzer collection failed. Check server logs and connectivity.'
            result={'state':'unavailable'}
        finished=self.clock()
        with store.database(path) as db:
            state=store.lifecycle(db,key)
            if not state['deleted'] and key in set(self.keys()):
                db.execute('''UPDATE collection_schedule SET next_at=?,state=?,error=?,
                    success_at=CASE WHEN ? THEN ? ELSE success_at END WHERE public_key=?''',
                    (finished+(SPACING if result.get('state')=='busy' else INTERVAL),result.get('state','unavailable'),error,success,result.get('fetched_at'),key))
            if result.get('state') in ('blocked','rate_limited'):
                # A provider restriction pauses the whole queue, including across
                # restarts. No immediate retry or fan-out to other managed keys.
                db.execute('UPDATE collection_control SET next_at=? WHERE id=1',
                    (max(finished+INTERVAL,self.analyzer.blocked_until),))
        return True

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logging.getLogger(__name__).exception('Analyzer collector scheduler unavailable')
            self.stop_event.wait(SPACING)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread=threading.Thread(target=self._run,name='analyzer-history',daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=35)


collector=AnalyzerCollector()
