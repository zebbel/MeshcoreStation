"""Explicit one-time collection grants and bounded job status, not polling settings."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import time
import uuid
from meshcorestation.storage.connection import connect
from meshcorestation.storage.voltage_store import MEMBERSHIP_LOCK

MAX_SECONDS=900
SCHEMA='''CREATE TABLE IF NOT EXISTS neighbor_snr_manual(
 public_key TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE,membership_since_ns INTEGER NOT NULL,
 state TEXT NOT NULL,requested_at REAL NOT NULL,expires_at REAL NOT NULL,started_at REAL,finished_at REAL,
 records INTEGER NOT NULL DEFAULT 0,pages INTEGER NOT NULL DEFAULT 0,protocol TEXT NOT NULL DEFAULT '',
 progress TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '');
 CREATE INDEX IF NOT EXISTS neighbor_snr_manual_state ON neighbor_snr_manual(state,requested_at);
 CREATE TRIGGER IF NOT EXISTS neighbor_snr_manual_unmanage AFTER UPDATE OF managed ON voltage_config
 WHEN NEW.managed=0 BEGIN
 UPDATE neighbor_snr_manual SET state='cancelled',finished_at=CAST(strftime('%s','now') AS REAL),
 error='Repeater removed from management; one-time authorization revoked.'
 WHERE public_key=NEW.public_key AND state IN ('queued','running');
 END;'''


class Busy(ValueError):pass


def _expire(db):
    db.execute("UPDATE neighbor_snr_manual SET state='cancelled',finished_at=?,error='Manual read authorization expired; request a new read explicitly.' WHERE state IN ('queued','running') AND expires_at<=?",(time.time(),time.time()))


def enqueue(path,key):
    from meshcorestation.storage.neighbor_snr import current
    if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('Select a complete managed repeater key.')
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as db,db:
        db.execute('BEGIN IMMEDIATE');configuration=current(db,key);_expire(db)
        if db.execute("SELECT 1 FROM neighbor_snr_manual WHERE state IN ('queued','running')").fetchone():raise Busy('A manual neighbor SNR read is already pending or running.')
        now=time.time();job=uuid.uuid4().hex
        db.execute('''INSERT INTO neighbor_snr_manual(public_key,job_id,membership_since_ns,state,requested_at,expires_at,progress)
          VALUES(?,?,?,'queued',?,?,?) ON CONFLICT(public_key) DO UPDATE SET job_id=excluded.job_id,
          membership_since_ns=excluded.membership_since_ns,state='queued',requested_at=excluded.requested_at,
          expires_at=excluded.expires_at,started_at=NULL,finished_at=NULL,records=0,pages=0,protocol='',progress=excluded.progress,error='' ''',
          (key,job,configuration['membership_since_ns'],now,now+MAX_SECONDS,'Queued; waiting for the existing neighbor collector and radio control lock.'))
        return dict(db.execute('SELECT * FROM neighbor_snr_manual WHERE public_key=?',(key,)).fetchone())


def snapshot(path,key):
    from meshcorestation.storage.neighbor_snr import managed
    with closing(connect(Path(path).as_uri()+'?mode=ro',timeout=.25)) as db:
        managed(db,key)
        row=db.execute('SELECT * FROM neighbor_snr_manual WHERE public_key=?',(key,)).fetchone()
        busy=db.execute("SELECT 1 FROM neighbor_snr_manual WHERE state IN ('queued','running') AND expires_at>?",(time.time(),)).fetchone()
        return dict(job=dict(row) if row else None,busy=bool(busy))


def pending(path):
    with closing(connect(path,timeout=.25)) as db,db:
        _expire(db)
        row=db.execute("SELECT m.* FROM neighbor_snr_manual m JOIN voltage_config v USING(public_key) WHERE m.state='queued' AND v.managed=1 AND v.statistics_since_ns=m.membership_since_ns ORDER BY requested_at LIMIT 1").fetchone()
        return dict(row) if row else None


def claim(path,job):
    from meshcorestation.storage.neighbor_snr import current
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as db,db:
        db.execute('BEGIN IMMEDIATE');_expire(db)
        try:cfg=current(db,job['public_key'])
        except ValueError:return None
        if cfg['membership_since_ns']!=job['membership_since_ns']:return None
        changed=db.execute("UPDATE neighbor_snr_manual SET state='running',started_at=?,progress='Reading neighbor SNR…' WHERE public_key=? AND job_id=? AND state='queued' AND expires_at>?",
            (time.time(),job['public_key'],job['job_id'],time.time())).rowcount
        if not changed:return None
        cfg['manual_job_id']=job['job_id']
        return cfg


def authorized(db,cfg):
    row=db.execute('''SELECT 1 FROM neighbor_snr_manual m JOIN voltage_config v USING(public_key)
      WHERE m.public_key=? AND m.job_id=? AND m.state='running' AND m.expires_at>?
      AND v.managed=1 AND v.statistics_since_ns=m.membership_since_ns AND m.membership_since_ns=?''',
      (cfg['public_key'],cfg.get('manual_job_id'),time.time(),cfg['membership_since_ns'])).fetchone()
    return bool(row)


def progress(path,cfg,text,records,protocol):
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as db,db:
        if not authorized(db,cfg):return False
        db.execute('UPDATE neighbor_snr_manual SET progress=?,records=?,pages=pages+1,protocol=? WHERE public_key=? AND job_id=?',
            (text[:300],records,protocol,cfg['public_key'],cfg['manual_job_id']))
        return True


def finish(path,cfg,error='',partial=False):
    # Recover accurate committed counts even if revocation raced the progress
    # update. This changes job metadata only; a revoked grant stays revoked.
    from meshcorestation.storage.passive_stats import statistics_path
    records=0;protocol=''
    target=statistics_path(path,cfg['public_key'])
    if target.exists():
        with closing(sqlite3.connect(target.as_uri()+'?mode=ro',uri=True,timeout=.25)) as history:
            if history.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_snr_aggregate_collections'").fetchone():
                row=history.execute('SELECT records FROM neighbor_snr_aggregate_collections WHERE poll_id=?',(cfg['manual_job_id'],)).fetchone()
                if row:records=row[0];protocol='averaged'
            if history.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_snr_readings'").fetchone():
                count=history.execute('SELECT COUNT(*) FROM neighbor_snr_readings WHERE poll_id=?',(cfg['manual_job_id'],)).fetchone()[0]
                if count:records=count;protocol='legacy'
    with closing(connect(path,timeout=.25)) as db,db:
        row=db.execute('SELECT records FROM neighbor_snr_manual WHERE public_key=? AND job_id=?',(cfg['public_key'],cfg['manual_job_id'])).fetchone()
        if not row:return
        records=max(records,row[0]);state='partial' if partial or (error and records) else 'error' if error else 'complete'
        db.execute("UPDATE neighbor_snr_manual SET records=?,protocol=CASE WHEN ?='' THEN protocol ELSE ? END WHERE public_key=? AND job_id=?",
            (records,protocol,protocol,cfg['public_key'],cfg['manual_job_id']))
        db.execute("UPDATE neighbor_snr_manual SET state=?,finished_at=?,error=?,progress=? WHERE public_key=? AND job_id=? AND state='running'",
            (state,time.time(),error[:300],'Manual collection finished; saved observations retained.',cfg['public_key'],cfg['manual_job_id']))


def cancel_pending(path,reason):
    with closing(connect(path,timeout=.25)) as db,db:
        db.execute("UPDATE neighbor_snr_manual SET state='interrupted',finished_at=?,error=? WHERE state IN ('queued','running')",(time.time(),reason[:300]))
