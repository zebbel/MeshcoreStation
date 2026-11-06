"""Opt-in repeater-side neighbor readings; independent of passive packet recording."""
from contextlib import closing
import json
import math
import re
from pathlib import Path
import shutil
import sqlite3
import time
from meshcorestation.storage.connection import connect
from meshcorestation.storage import passive_stats
from meshcorestation.storage.voltage_store import MEMBERSHIP_LOCK
from meshcorestation.radio.neighbor_names import with_neighbor_names

MIN_INTERVAL=5
MAX_INTERVAL=1440
SCHEMA='''CREATE TABLE IF NOT EXISTS neighbor_monitor(
 public_key TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 0,interval_minutes INTEGER NOT NULL DEFAULT 30,
 revision INTEGER NOT NULL DEFAULT 0,next_due REAL NOT NULL DEFAULT 0,last_attempt REAL,
 last_success REAL,state TEXT NOT NULL DEFAULT 'disabled',error TEXT NOT NULL DEFAULT '');'''
HISTORY_SCHEMA='''CREATE TABLE IF NOT EXISTS neighbor_snr_polls(
 id TEXT PRIMARY KEY,started_at REAL NOT NULL,finished_at REAL,complete INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '');
 CREATE TABLE IF NOT EXISTS neighbor_snr_measurements(
 id INTEGER PRIMARY KEY,prefix TEXT NOT NULL,public_key TEXT,resolution TEXT NOT NULL,
 snr REAL NOT NULL,heard_lo REAL NOT NULL,heard_hi REAL NOT NULL,first_polled REAL NOT NULL,last_polled REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS neighbor_snr_time ON neighbor_snr_measurements(heard_hi,heard_lo);
 CREATE INDEX IF NOT EXISTS neighbor_snr_dedup ON neighbor_snr_measurements(prefix,last_polled);
 CREATE INDEX IF NOT EXISTS neighbor_snr_identity ON neighbor_snr_measurements(public_key,resolution,snr,heard_hi);
 CREATE INDEX IF NOT EXISTS neighbor_snr_estimated_time ON neighbor_snr_measurements((heard_lo+heard_hi)/2);
 CREATE TABLE IF NOT EXISTS neighbor_snr_readings(
 id INTEGER PRIMARY KEY,poll_id TEXT NOT NULL,polled_at REAL NOT NULL,prefix TEXT NOT NULL,
 public_key TEXT,resolution TEXT NOT NULL,snr REAL,secs_ago INTEGER,raw TEXT NOT NULL,measurement_id INTEGER);
 CREATE INDEX IF NOT EXISTS neighbor_snr_reading_time ON neighbor_snr_readings(polled_at);'''


def managed(db,key):
    if not db.execute('SELECT 1 FROM voltage_config WHERE public_key=? AND managed=1',(key,)).fetchone():
        raise ValueError('Select a managed repeater.')


def current(db,key):
    managed(db,key)
    row=db.execute('SELECT * FROM neighbor_monitor WHERE public_key=?',(key,)).fetchone()
    value=dict(row) if row else dict(public_key=key,enabled=0,interval_minutes=30,revision=0,next_due=0,last_attempt=None,last_success=None,state='disabled',error='')
    value['membership_since_ns']=db.execute('SELECT statistics_since_ns FROM voltage_config WHERE public_key=?',(key,)).fetchone()[0]
    return value


def settings(path,key):
    with closing(connect(Path(path).as_uri()+'?mode=ro',timeout=.25)) as db:return current(db,key)


def save_settings(path,key,enabled,interval):
    if type(enabled) is not bool or type(interval) is not int or not MIN_INTERVAL<=interval<=MAX_INTERVAL:
        raise ValueError('Choose enabled/disabled and an interval from 5 to 1440 whole minutes.')
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as db,db:
        managed(db,key)
        db.execute('''INSERT INTO neighbor_monitor(public_key,enabled,interval_minutes,revision,next_due,state)
          VALUES(?,?,?,1,?,?) ON CONFLICT(public_key) DO UPDATE SET enabled=excluded.enabled,
          interval_minutes=excluded.interval_minutes,revision=neighbor_monitor.revision+1,
          next_due=excluded.next_due,state=excluded.state,error='' ''',
          (key,int(enabled),interval,time.time() if enabled else 0,'scheduled' if enabled else 'disabled'))
        return current(db,key)


def due(path,now):
    with closing(connect(Path(path).as_uri()+'?mode=ro',timeout=.25)) as db:
        return [dict(r) for r in db.execute('''SELECT n.*,v.statistics_since_ns AS membership_since_ns FROM neighbor_monitor n JOIN voltage_config v USING(public_key)
          WHERE v.managed=1 AND n.enabled=1 AND n.next_due<=? ORDER BY n.next_due,n.public_key''',(now,))]


def claim(path,cfg,now):
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as db,db:
        try:latest=current(db,cfg['public_key'])
        except ValueError:return False
        if not latest['enabled'] or latest['revision']!=cfg['revision'] or latest['membership_since_ns']!=cfg['membership_since_ns'] or latest['next_due']>now:return False
        db.execute("UPDATE neighbor_monitor SET next_due=?,last_attempt=?,state='collecting',error='' WHERE public_key=?",
                   (now+cfg['interval_minutes']*60,now,cfg['public_key']))
        return True


def still_enabled(path,cfg):
    try:
        row=settings(path,cfg['public_key'])
        return row['enabled'] and row['revision']==cfg['revision'] and row['membership_since_ns']==cfg['membership_since_ns']
    except ValueError:return False


def finish(path,cfg,poll_id,stamp,error=''):
    with closing(connect(path,timeout=.25)) as main,main:
        main.execute('''UPDATE neighbor_monitor SET next_due=MAX(next_due,?+interval_minutes*60),state=?,error=?,last_success=CASE WHEN ?='' THEN ? ELSE last_success END
          WHERE public_key=? AND revision=?''',(stamp,'error' if error else 'waiting',error,error,stamp,cfg['public_key'],cfg['revision']))
    target=passive_stats.statistics_path(path,cfg['public_key'])
    if target.exists():
        with closing(sqlite3.connect(target,timeout=.25)) as db,db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_snr_polls'").fetchone():
                db.execute('UPDATE neighbor_snr_polls SET finished_at=?,complete=?,error=? WHERE id=?',(stamp,int(not error),error,poll_id))


def record_page(path,cfg,poll_id,started,received,rows):
    """Recheck opt-in/membership at commit; preserve raw polls, dedup age intervals.

    The repeater supplies an age, not a reception ID. The source event is bounded
    by request start/response arrival (plus age rounding); intersecting equal-SNR
    intervals are conservatively treated as the same reading, not independent RX.
    """
    with MEMBERSHIP_LOCK,closing(connect(Path(path).as_uri()+'?mode=ro',timeout=.25)) as main:
        try:latest=current(main,cfg['public_key'])
        except ValueError:return False
        if not latest['enabled'] or latest['revision']!=cfg['revision'] or latest['membership_since_ns']!=cfg['membership_since_ns']:return False
        named=with_neighbor_names(main,{'neighbours':rows})['neighbours']
        if shutil.disk_usage(Path(path).parent).free<passive_stats.MIN_FREE_BYTES:raise OSError('Low disk space; existing history is preserved.')
        target=passive_stats.statistics_path(path,cfg['public_key'])
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not target.exists():target.touch(mode=0o600)
        with closing(sqlite3.connect(target,timeout=.25)) as db:
            db.execute('PRAGMA journal_mode=WAL');db.executescript(passive_stats.SCHEMA+HISTORY_SCHEMA)
            with db:
                db.execute('INSERT OR IGNORE INTO neighbor_snr_polls(id,started_at) VALUES(?,?)',(poll_id,started))
                for r in named:
                    prefix=r['pubkey'];snr=r.get('snr');age=r.get('secs_ago');measurement=None
                    valid_snr=type(snr) in (int,float) and math.isfinite(snr) and -32<=snr<=31.75
                    valid_age=type(age) is int and 0<=age<=2147483647
                    valid_prefix=bool(re.fullmatch('[0-9a-f]{2,64}',prefix)) and len(prefix)%2==0
                    if valid_snr and valid_age and valid_prefix:
                        lo,hi=started-age-1,received-age+1
                        previous=db.execute('''SELECT id,heard_lo,heard_hi FROM neighbor_snr_measurements
                          WHERE ((public_key IS NOT NULL AND public_key=?) OR (public_key IS NULL AND prefix=?)) AND resolution=? AND snr=?
                          AND heard_lo<=? AND heard_hi>=? ORDER BY last_polled DESC LIMIT 1''',
                          (r.get('public_key'),prefix,r['resolution'],snr,hi,lo)).fetchone()
                        if previous:
                            measurement=previous[0]
                            db.execute('UPDATE neighbor_snr_measurements SET heard_lo=?,heard_hi=?,last_polled=? WHERE id=?',
                                       (max(lo,previous[1]),min(hi,previous[2]),received,measurement))
                        else:
                            measurement=db.execute('''INSERT INTO neighbor_snr_measurements
                              (prefix,public_key,resolution,snr,heard_lo,heard_hi,first_polled,last_polled) VALUES(?,?,?,?,?,?,?,?)''',
                              (prefix,r.get('public_key'),r['resolution'],snr,lo,hi,received,received)).lastrowid
                    raw=json.dumps({k:r.get(k) if type(r.get(k)) not in (float,) or math.isfinite(r[k]) else str(r[k]) for k in ('pubkey','snr','secs_ago')})
                    db.execute('''INSERT INTO neighbor_snr_readings(poll_id,polled_at,prefix,public_key,resolution,snr,secs_ago,raw,measurement_id)
                      VALUES(?,?,?,?,?,?,?,?,?)''',(poll_id,received,prefix,r.get('public_key'),r['resolution'],snr if valid_snr else None,age if valid_age else None,raw,measurement))
        return True


def _legacy_summary(source,registry,start,end):
    """SQL groups only; raw poll history never enters the browser."""
    if not source.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_snr_measurements'").fetchone():return []
    rows=source.execute('''SELECT prefix,public_key,resolution,AVG(snr),COUNT(*),MAX((heard_lo+heard_hi)/2)
      FROM neighbor_snr_measurements WHERE (heard_lo+heard_hi)/2>=? AND (heard_lo+heard_hi)/2<?
      GROUP BY prefix,public_key,resolution ORDER BY COUNT(*) DESC,prefix''',(start,end))
    result=[]
    for prefix,key,status,average,count,last in rows:
        matches=[k for k in registry if k.startswith(prefix)]
        resolved=status=='matched' and len(matches)==1 and matches[0]==key
        result.append(dict(prefix=prefix,public_key=key if resolved else None,resolution='matched' if resolved else 'ambiguous' if len(matches)>1 or status=='ambiguous' else 'unknown',
                           name=registry.get(key,{}).get('name') if resolved else None,average_snr=average,samples=count,last_heard=last))
    grouped={}
    for row in result:
        identity=row['public_key'] or (row['prefix'],row['resolution'])
        if identity not in grouped:grouped[identity]=row
        else:
            old=grouped[identity];n=old['samples']+row['samples']
            old['average_snr']=(old['average_snr']*old['samples']+row['average_snr']*row['samples'])/n
            old['samples']=n;old['last_heard']=max(old['last_heard'],row['last_heard'])
    return list(grouped.values())


def summary(source,registry,start,end,quality=None):
    from meshcorestation.storage.averaged_snr import summary as aggregated
    legacy=_legacy_summary(source,registry,start,end)
    firmware,details=aggregated(source,registry,start,end)
    if quality is not None:quality.update(details)
    firmware_keys={r['public_key'] for r in firmware}
    for row in legacy:row.update(source='legacy_last_heard',minimum_snr=None,maximum_snr=None)
    # Preserve legacy history but do not blend differently sampled methods.
    return firmware+[r for r in legacy if r['public_key'] not in firmware_keys]
