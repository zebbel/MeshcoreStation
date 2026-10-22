"""Persist per-repeater roles, opted-in neighbor schedules and bounded snapshots."""
import re
import sqlite3
import time
import threading
from functools import wraps
from contextlib import closing
from meshcorestation.config import DATA_DIR

LOCK = threading.RLock()


def synchronized(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with LOCK:
            return fn(*args, **kwargs)
    return call


FILE = DATA_DIR / 'repeater-optimizer.db'
ROLES = ('unknown', 'local', 'regional', 'hybrid')
INTERVALS = {'manual': 0, '24h': 86400, '12h': 43200}
DEFAULTS = {'retention_days': 60, 'neighbor_days': 90, 'summary_days': 365,
            'budget_mb': 3072, 'reserve_mb': 4096}


def connect():
    FILE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(FILE, timeout=5)
    db.row_factory = sqlite3.Row
    return db


@synchronized
def initialize():
    with closing(connect()) as db, db:
        db.executescript("""
          DROP TABLE IF EXISTS downtime;
          CREATE TABLE IF NOT EXISTS lifecycle (
            id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL, since REAL NOT NULL);
          INSERT OR IGNORE INTO lifecycle VALUES(1,1,0);
          CREATE TABLE IF NOT EXISTS profiles (
            public_key TEXT PRIMARY KEY, role TEXT NOT NULL DEFAULT 'unknown',
            polling TEXT NOT NULL DEFAULT 'manual', next_poll REAL,
            last_poll REAL, last_error TEXT DEFAULT '');
          CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY, public_key TEXT NOT NULL, at REAL NOT NULL,
            source TEXT NOT NULL, reported INTEGER, complete INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS snapshots_key_at ON snapshots(public_key,at);
          CREATE TABLE IF NOT EXISTS neighbors (
            snapshot_id INTEGER NOT NULL, neighbor_key TEXT NOT NULL,
            snr REAL, secs_ago REAL);
          CREATE TABLE IF NOT EXISTS config (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
        """)
        for key, value in DEFAULTS.items():
            db.execute('INSERT OR IGNORE INTO config VALUES(?,?)', (key, value))


def valid_key(key):
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('Invalid repeater key.')
    return key


def config():
    with closing(connect()) as db:
        return {**DEFAULTS, **dict(db.execute('SELECT name,value FROM config'))}


@synchronized
def update_config(values):
    limits = {'retention_days': (1,180), 'neighbor_days':(7,365),
              'summary_days':(30,730), 'budget_mb':(256,16384), 'reserve_mb':(1024,16384)}
    if not isinstance(values, dict) or set(values) != set(limits):
        raise ValueError('Invalid storage settings.')
    for name, (low,high) in limits.items():
        if type(values[name]) is not int or not low <= values[name] <= high:
            raise ValueError(f'{name}: choose {low}–{high}.')
    with closing(connect()) as db, db:
        db.executemany('INSERT OR REPLACE INTO config VALUES(?,?)', values.items())
    return config()


def profile(key):
    valid_key(key)
    with closing(connect()) as db:
        row = db.execute('SELECT * FROM profiles WHERE public_key=?', (key,)).fetchone()
        return dict(row) if row else {'public_key':key,'role':'unknown','polling':'manual',
                                      'next_poll':None,'last_poll':None,'last_error':''}


@synchronized
def update_profile(key, role, polling):
    if not status()['enabled']:
        raise ValueError('Repeater Optimizer is disabled. Enable it in Settings.')
    valid_key(key)
    if role not in ROLES or polling not in INTERVALS:
        raise ValueError('Invalid repeater role or polling interval.')
    now = time.time()
    with closing(connect()) as db, db:
        old = db.execute('SELECT polling,next_poll FROM profiles WHERE public_key=?', (key,)).fetchone()
        next_at = (old['next_poll'] if old and old['polling']==polling else
                   now+INTERVALS[polling] if INTERVALS[polling] else None)
        db.execute("""INSERT INTO profiles(public_key,role,polling,next_poll) VALUES(?,?,?,?)
            ON CONFLICT(public_key) DO UPDATE SET role=excluded.role,
             polling=excluded.polling,next_poll=excluded.next_poll""", (key,role,polling,next_at))
    return profile(key)


def due(now=None):
    if not status()['enabled']:
        return None
    now = time.time() if now is None else now
    with closing(connect()) as db:
        row = db.execute("""SELECT * FROM profiles WHERE polling!='manual'
              AND next_poll IS NOT NULL AND next_poll<=? ORDER BY next_poll LIMIT 1""", (now,)).fetchone()
        return dict(row) if row else None


@synchronized
def claim_poll(key, now=None):
    """Advance deadline before RF; never queue missed polls or auto-retry."""
    if not status()['enabled']:
        return False
    now = time.time() if now is None else now
    with closing(connect()) as db, db:
        row = db.execute('SELECT polling FROM profiles WHERE public_key=?', (key,)).fetchone()
        if not row or row['polling']=='manual':
            return False
        db.execute('UPDATE profiles SET next_poll=?,last_poll=?,last_error=? WHERE public_key=?',
                   (now+INTERVALS[row['polling']],now,'',key))
    return True


@synchronized
def poll_error(key, reason, started_at=None):
    state = status()
    if not state['enabled'] or (started_at is not None and started_at < state['since']):
        return
    with closing(connect()) as db, db:
        db.execute('UPDATE profiles SET last_error=? WHERE public_key=?', (str(reason)[:160],key))


@synchronized
def save_neighbors(key, data, source='manual', started_at=None):
    state = status()
    if not state['enabled'] or (started_at is not None and started_at < state['since']):
        return None
    valid_key(key)
    if source not in ('manual','scheduled') or not isinstance(data,dict) or not isinstance(data.get('neighbours'),list):
        raise ValueError('Invalid neighbor response.')
    rows=data['neighbours'][:15]
    parsed=[]
    for neighbor in rows:
        if not isinstance(neighbor,dict):
            continue
        peer=str(neighbor.get('pubkey') or '').lower()
        # meshcore_py 2.3.14 requests four-byte public-key prefixes by
        # default (eight hex characters), not six-byte / 12-character ones.
        # Some firmware and clients use other prefix sizes; each prefix must
        # represent whole bytes. Store it as a prefix, never a verified key.
        if not re.fullmatch('[0-9a-f]{2,64}',peer) or len(peer)%2:
            continue
        snr,age=neighbor.get('snr'),neighbor.get('secs_ago')
        parsed.append((peer,float(snr) if type(snr) in (int,float) and abs(snr)<1000 else None,
                       float(age) if type(age) in (int,float) and 0<=age<1e8 else None))
    count=data.get('neighbours_count')
    count=count if type(count) is int and count>=0 else None
    if rows and not parsed:
        # A successful radio request whose neighbor entries we cannot decode
        # must not be cached as a genuinely empty neighbor list.
        raise ValueError('Neighbor response contained entries, but none had a valid public-key prefix.')
    if count and not parsed:
        raise ValueError('Repeater reported neighbors, but no usable neighbor entries were decoded.')
    at=time.time()
    with closing(connect()) as db, db:
        snapshot_id=db.execute('INSERT INTO snapshots(public_key,at,source,reported,complete) VALUES(?,?,?,?,?)',
                       (key,at,source,count,int(count is not None and count<=len(parsed)))).lastrowid
        db.executemany('INSERT INTO neighbors VALUES(?,?,?,?)',[(snapshot_id,*item) for item in parsed])
    # Re-open the database to verify the saved count that the optimizer's
    # separate HTTP worker will read. Do not claim success without persistence.
    with closing(connect()) as check:
        stored=check.execute('SELECT COUNT(*) FROM neighbors WHERE snapshot_id=?',(snapshot_id,)).fetchone()[0]
    if stored!=len(parsed):
        raise sqlite3.DatabaseError('Neighbor snapshot verification failed.')
    return {'id':snapshot_id,'at':at,'neighbors':stored,'received':len(rows),
            'reported':count,'complete':count is not None and count<=stored}


def snapshots(key, limit=15):
    valid_key(key)
    with closing(connect()) as db:
        result=[dict(r) for r in db.execute('SELECT * FROM snapshots WHERE public_key=? ORDER BY at DESC,id DESC LIMIT ?',(key,limit))]
        for row in result:
            row['neighbors']=[dict(r) for r in db.execute('SELECT neighbor_key,snr,secs_ago FROM neighbors WHERE snapshot_id=?',(row['id'],))]
        return result


@synchronized
def cleanup(now=None):
    cutoff=(time.time() if now is None else now)-config()['neighbor_days']*86400
    with closing(connect()) as db, db:
        db.execute('DELETE FROM neighbors WHERE snapshot_id IN (SELECT id FROM snapshots WHERE at<?)',(cutoff,))
        db.execute('DELETE FROM snapshots WHERE at<?',(cutoff,))


@synchronized
def remove_repeater(key):
    """Discard optimizer role, polling and snapshots for a removed managed repeater."""
    valid_key(key)
    if not FILE.exists():
        return
    with closing(connect()) as db, db:
        db.execute('DELETE FROM neighbors WHERE snapshot_id IN '
                   '(SELECT id FROM snapshots WHERE public_key=?)', (key,))
        db.execute('DELETE FROM snapshots WHERE public_key=?', (key,))
        db.execute('DELETE FROM profiles WHERE public_key=?', (key,))


@synchronized
def status():
    """Read persisted lifecycle state; migrate an existing installation on first use."""
    with closing(connect()) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='lifecycle'").fetchone()
    if not exists:
        initialize()
    with closing(connect()) as db:
        row = db.execute('SELECT enabled,since FROM lifecycle WHERE id=1').fetchone()
        return {'enabled': bool(row['enabled']), 'since': row['since']}


@synchronized
def reset(enabled=None):
    """Clear optimizer-owned tables globally, preserving ordinary statistics.

    The collector and other optimizer writers share LOCK. The cutoff also
    rejects packets and radio responses queued before the reset.
    """
    from meshcorestation.storage import passive_stats, advisor_history
    state = status()
    if enabled is not None and type(enabled) is not bool:
        raise ValueError('Enabled must be true or false.')
    enabled = state['enabled'] if enabled is None else enabled
    passive_stats.initialize()
    with advisor_history.database():
        pass
    with closing(connect()) as db:
        db.execute('ATTACH DATABASE ? AS packets', (str(passive_stats.STATS_PATH),))
        db.execute('ATTACH DATABASE ? AS audit', (str(advisor_history.FILE),))
        with db:
            db.execute('UPDATE lifecycle SET enabled=?,since=? WHERE id=1', (int(enabled),time.time()))
            for table in ('neighbors','snapshots','profiles'):
                db.execute('DELETE FROM '+table)
            db.execute('DELETE FROM packets.network_observations')
            db.execute('DELETE FROM packets.network_daily')
            db.execute('DELETE FROM audit.changes')
    return status()


@synchronized
def set_enabled(enabled):
    if type(enabled) is not bool:
        raise ValueError('Enabled must be true or false.')
    if status()['enabled'] == enabled:
        return status()
    return reset(enabled)
