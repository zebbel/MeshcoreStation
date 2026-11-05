"""Persistent opt-in schedules; no credentials and no changes to observation history."""
from contextlib import closing
from pathlib import Path
import re
import json
import time
from meshcorestation.storage.connection import connect
from meshcorestation.storage.voltage_store import MEMBERSHIP_LOCK

INTERVALS = (1, 3, 6, 12, 24, 48, 72, 168)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS repeater_clock_sync(
 public_key TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
 interval_hours INTEGER NOT NULL DEFAULT 24, revision INTEGER NOT NULL DEFAULT 0,
 last_attempt REAL, last_success REAL, next_due REAL, clock_offset REAL,
 state TEXT NOT NULL DEFAULT 'disabled', error TEXT NOT NULL DEFAULT '',
 uncertain INTEGER NOT NULL DEFAULT 0, last_result TEXT);
CREATE INDEX IF NOT EXISTS clock_sync_due ON repeater_clock_sync(enabled,next_due);
CREATE TRIGGER IF NOT EXISTS clock_sync_unmanage AFTER UPDATE OF managed ON voltage_config
 WHEN NEW.managed=0 BEGIN
 UPDATE repeater_clock_sync SET enabled=0,revision=revision+1,next_due=NULL,state='disabled',
 error=CASE WHEN uncertain=1 THEN 'Previous clock write requires manual verification.' ELSE '' END
 WHERE public_key=NEW.public_key;
 END;
'''


def current(db, key):
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('Select a complete managed repeater public key.')
    member = db.execute('SELECT statistics_since_ns FROM voltage_config WHERE public_key=? AND managed=1', (key,)).fetchone()
    if not member:
        raise ValueError('Select a managed repeater.')
    row = db.execute('SELECT * FROM repeater_clock_sync WHERE public_key=?', (key,)).fetchone()
    value = dict(row) if row else dict(public_key=key, enabled=0, interval_hours=24, revision=0,
        last_attempt=None, last_success=None, next_due=None, clock_offset=None, state='disabled', error='', uncertain=0, last_result=None)
    if isinstance(value['last_result'], str):
        value['last_result'] = json.loads(value['last_result'])
    value['membership_since_ns'] = member[0]
    return value


def settings(path, key):
    with closing(connect(Path(path).as_uri()+'?mode=ro', timeout=.25)) as db:
        return current(db, key)


def save(path, key, enabled, interval, revision, acknowledge=False):
    if type(enabled) is not bool or type(interval) is not int or interval not in INTERVALS or type(revision) is not int or type(acknowledge) is not bool:
        raise ValueError('Choose enabled/disabled and a supported whole-hour interval.')
    with MEMBERSHIP_LOCK, closing(connect(path, timeout=.25)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        old = current(db, key)
        if old['revision'] != revision:
            raise ValueError('Clock settings changed. Reload before saving.')
        if enabled and old['state']=='writing':
            raise ValueError('Clock command is in progress. Wait for its result before resuming.')
        if enabled and old['uncertain'] and not acknowledge:
            raise ValueError('Manually verify the repeater clock before explicitly resuming an uncertain write.')
        uncertain = old['uncertain'] and not (enabled and acknowledge)
        db.execute('''INSERT INTO repeater_clock_sync(public_key) VALUES(?) ON CONFLICT DO NOTHING''', (key,))
        db.execute('''UPDATE repeater_clock_sync SET enabled=?,interval_hours=?,revision=revision+1,
          next_due=?,state=?,error=?,uncertain=? WHERE public_key=?''',
          (int(enabled), interval, time.time()+60 if enabled else None,
           'scheduled' if enabled else 'disabled', 'Previous clock write requires manual verification.' if uncertain else old['error'], int(uncertain), key))
        return current(db, key)


def active(db, cfg):
    try:
        row = current(db, cfg['public_key'])
    except ValueError:
        return False
    return bool(row['enabled'] and row['revision']==cfg['revision'] and row['membership_since_ns']==cfg['membership_since_ns'])


def still_enabled(path, cfg):
    with closing(connect(Path(path).as_uri()+'?mode=ro', timeout=.25)) as db:
        return active(db, cfg)


def due(path, now):
    with closing(connect(Path(path).as_uri()+'?mode=ro', timeout=.25)) as db:
        rows = db.execute('''SELECT c.public_key FROM repeater_clock_sync c JOIN voltage_config v USING(public_key)
          WHERE v.managed=1 AND c.enabled=1 AND c.uncertain=0 AND c.next_due<=?
          AND c.state NOT IN ('checking','writing') ORDER BY c.next_due,c.public_key LIMIT 1''', (now,))
        return [current(db, row[0]) for row in rows]


def claim(path, cfg, now):
    with MEMBERSHIP_LOCK, closing(connect(path, timeout=.25)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if not active(db, cfg): return False
        row = current(db, cfg['public_key'])
        if row['uncertain'] or row['state'] in ('checking','writing') or row['next_due'] is None or row['next_due']>now: return False
        db.execute("UPDATE repeater_clock_sync SET last_attempt=?,next_due=?,state='checking',error='',last_result=NULL WHERE public_key=?",
                   (now, now+cfg['interval_hours']*3600, cfg['public_key']))
        return True


def mark_write(path, cfg):
    """Durable uncertainty fence BEFORE handing a write to the transport."""
    with MEMBERSHIP_LOCK, closing(connect(path, timeout=.25)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if not active(db, cfg): return False
        row = current(db, cfg['public_key'])
        if row['uncertain']: return False
        db.execute("UPDATE repeater_clock_sync SET uncertain=1,state='writing' WHERE public_key=?", (cfg['public_key'],))
        return True


def finish(path, cfg, state, error='', offset=None, success=False, verified=False, latency=0):
    now = time.time()
    with closing(connect(path, timeout=.25)) as db, db:
        if cfg.get('attempt_started') is not None:
            result = dict(state=state,error=error[:300],clock_offset=offset,success=bool(success),finished_at=now,latency_allowance_seconds=latency)
            db.execute('UPDATE repeater_clock_sync SET last_result=? WHERE public_key=? AND last_attempt=?',
                       (json.dumps(result),cfg['public_key'],cfg['attempt_started']))
        db.execute('''UPDATE repeater_clock_sync SET state=?,error=?,clock_offset=COALESCE(?,clock_offset),
          last_success=CASE WHEN ? THEN ? ELSE last_success END,
          uncertain=CASE WHEN ? THEN 0 ELSE uncertain END,
          next_due=CASE WHEN uncertain=1 AND NOT ? THEN NULL ELSE MAX(COALESCE(next_due,0),?+interval_hours*3600) END
          WHERE public_key=? AND revision=?''',
          (state, error[:300], offset, int(success), now, int(verified), int(verified), now, cfg['public_key'], cfg['revision']))


def recover(path):
    with closing(connect(path, timeout=.25)) as db, db:
        rows = db.execute("SELECT * FROM repeater_clock_sync WHERE (enabled=1 AND uncertain=1) OR state='checking'").fetchall()
        for row in rows:
            uncertain = bool(row['uncertain'])
            state = 'verification_required' if uncertain else 'interrupted'
            error = 'Clock write interrupted; manually verify the clock before resuming.' if uncertain else 'Previous clock check interrupted; the saved schedule is preserved.'
            result = json.dumps(dict(state=state,error=error,clock_offset=row['clock_offset'],success=False,finished_at=None))
            db.execute('''UPDATE repeater_clock_sync SET state=?,error=?,last_result=COALESCE(last_result,?),
              next_due=CASE WHEN uncertain=1 THEN NULL ELSE next_due END WHERE public_key=?''',
              (state,error,result,row['public_key']))
