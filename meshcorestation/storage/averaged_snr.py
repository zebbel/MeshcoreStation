"""Immutable firmware aggregates and per-repeater capability/checkpoint state."""
from contextlib import closing
from pathlib import Path
import json
import shutil
import sqlite3
import time
from meshcorestation.storage.connection import connect
from meshcorestation.storage.voltage_store import MEMBERSHIP_LOCK
from meshcorestation.storage import passive_stats

SCHEMA='''CREATE TABLE IF NOT EXISTS neighbor_snr_protocol(
 public_key TEXT PRIMARY KEY,capability TEXT NOT NULL DEFAULT 'unknown',detection TEXT NOT NULL DEFAULT 'unprobed',
 probe_after REAL NOT NULL DEFAULT 0,firmware_level INTEGER,session TEXT NOT NULL DEFAULT '',ceiling INTEGER NOT NULL DEFAULT 0,
 cursor INTEGER NOT NULL DEFAULT 0,seen_sequence INTEGER NOT NULL DEFAULT 0,pending INTEGER NOT NULL DEFAULT 0,
 last_collection REAL,last_window REAL,records_retrieved INTEGER NOT NULL DEFAULT 0,completeness TEXT NOT NULL DEFAULT 'not_collected',
 duration_seconds REAL,diagnostics TEXT NOT NULL DEFAULT '{}',warning TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '');'''
HISTORY_SCHEMA='''CREATE TABLE IF NOT EXISTS neighbor_snr_aggregates(
 public_key TEXT NOT NULL,session TEXT NOT NULL,sequence INTEGER NOT NULL,neighbor_key TEXT NOT NULL,window INTEGER NOT NULL,
 mono_start INTEGER NOT NULL,mono_end INTEGER NOT NULL,utc_start INTEGER,utc_end INTEGER,snr_sum INTEGER NOT NULL,
 sample_count INTEGER NOT NULL CHECK(sample_count>0),average_snr REAL GENERATED ALWAYS AS (snr_sum/(4.0*sample_count)) VIRTUAL,
 minimum INTEGER NOT NULL,maximum INTEGER NOT NULL,flags INTEGER NOT NULL,last_mono INTEGER NOT NULL,last_utc INTEGER,
 raw BLOB NOT NULL,retrieved_at REAL NOT NULL,PRIMARY KEY(public_key,session,sequence),UNIQUE(public_key,session,neighbor_key,window));
 CREATE INDEX IF NOT EXISTS snr_aggregate_utc ON neighbor_snr_aggregates(utc_end,utc_start,neighbor_key);
 CREATE INDEX IF NOT EXISTS snr_aggregate_start ON neighbor_snr_aggregates(utc_start,utc_end);
 CREATE INDEX IF NOT EXISTS snr_aggregate_neighbor ON neighbor_snr_aggregates(neighbor_key,utc_start,utc_end);
 CREATE TABLE IF NOT EXISTS neighbor_snr_aggregate_collections(
 poll_id TEXT PRIMARY KEY,started_at REAL NOT NULL,finished_at REAL,complete INTEGER NOT NULL DEFAULT 0,records INTEGER NOT NULL DEFAULT 0,
 session TEXT,diagnostics TEXT NOT NULL DEFAULT '{}',warning TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '');
 CREATE INDEX IF NOT EXISTS snr_aggregate_collection_time ON neighbor_snr_aggregate_collections(started_at);
 CREATE TABLE IF NOT EXISTS neighbor_snr_sequence_gaps(session TEXT NOT NULL,first_sequence INTEGER NOT NULL,last_sequence INTEGER NOT NULL,
 noticed_at REAL NOT NULL,PRIMARY KEY(session,first_sequence,last_sequence));
 CREATE INDEX IF NOT EXISTS snr_gap_time ON neighbor_snr_sequence_gaps(noticed_at);'''
FIELDS=('neighbor_key','sequence','window','mono_start','mono_end','utc_start','utc_end','snr_sum','sample_count','minimum','maximum','flags','last_mono','last_utc')
DEFAULTS=dict(capability='unknown',detection='unprobed',probe_after=0,firmware_level=None,session='',ceiling=0,cursor=0,seen_sequence=0,
    pending=0,last_collection=None,last_window=None,records_retrieved=0,completeness='not_collected',duration_seconds=None,diagnostics={},warning='',error='')


def status(path,key):
    with closing(connect(Path(path).as_uri()+'?mode=ro',timeout=.25)) as db:
        row=db.execute('SELECT * FROM neighbor_snr_protocol WHERE public_key=?',(key,)).fetchone()
    result=dict(row) if row else dict(DEFAULTS,public_key=key)
    if isinstance(result['diagnostics'],str):result['diagnostics']=json.loads(result['diagnostics'])
    return result


def _active(db,cfg):
    from meshcorestation.storage.neighbor_snr import current
    try:latest=current(db,cfg['public_key'])
    except ValueError:return False
    return bool(latest['enabled'] and latest['revision']==cfg['revision'] and latest['membership_since_ns']==cfg['membership_since_ns'])


def update(path,cfg,**values):
    if not values or not values.keys()<=DEFAULTS.keys():raise ValueError('Invalid SNR protocol status fields.')
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as db,db:
        if not _active(db,cfg):return False
        db.execute('INSERT OR IGNORE INTO neighbor_snr_protocol(public_key) VALUES(?)',(cfg['public_key'],))
        values={k:json.dumps(v) if k=='diagnostics' else v for k,v in values.items()}
        db.execute('UPDATE neighbor_snr_protocol SET '+','.join(k+'=?' for k in values)+' WHERE public_key=?',list(values.values())+[cfg['public_key']])
        return True


def recheck(path,key):
    from meshcorestation.storage.neighbor_snr import managed
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as db,db:
        managed(db,key)
        db.execute('INSERT OR IGNORE INTO neighbor_snr_protocol(public_key) VALUES(?)',(key,))
        db.execute("UPDATE neighbor_snr_protocol SET probe_after=0,detection='recheck_requested' WHERE public_key=?",(key,))


def record(path,cfg,poll_id,started,header,raw,warning='',gap=None):
    """Evidence commits before checkpoint advancement; a crash can replay safely."""
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as main:
        if not _active(main,cfg):return False
        if shutil.disk_usage(Path(path).parent).free<passive_stats.MIN_FREE_BYTES:raise OSError('Low disk space; saved SNR history is preserved.')
        target=passive_stats.statistics_path(path,cfg['public_key']);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not target.exists():target.touch(mode=0o600)
        with closing(sqlite3.connect(target,timeout=.25)) as db:
            db.execute('PRAGMA journal_mode=WAL');db.executescript(passive_stats.SCHEMA+HISTORY_SCHEMA)
            with db:
                db.execute('INSERT OR IGNORE INTO neighbor_snr_aggregate_collections(poll_id,started_at) VALUES(?,?)',(poll_id,started))
                item=header['record']
                if item:
                    values=[item[k] for k in FIELDS]
                    previous=db.execute('SELECT '+','.join(FIELDS)+',raw FROM neighbor_snr_aggregates WHERE public_key=? AND session=? AND sequence=?',
                        (cfg['public_key'],header['session'],item['sequence'])).fetchone()
                    if previous:
                        if tuple(previous)!=tuple(values)+(raw[64:140],):raise ValueError('Conflicting immutable SNR record; cursor not advanced.')
                    else:
                        db.execute('INSERT INTO neighbor_snr_aggregates(public_key,session,'+','.join(FIELDS)+',raw,retrieved_at) VALUES('+','.join('?' for _ in range(len(FIELDS)+4))+')',
                            [cfg['public_key'],header['session']]+values+[raw[64:140],time.time()])
                if gap and gap[0]<=gap[1]:db.execute('INSERT OR IGNORE INTO neighbor_snr_sequence_gaps VALUES(?,?,?,?)',(header['session'],gap[0],gap[1],time.time()))
                diagnostics={k:v for k,v in header.items() if k!='record'}
                db.execute('UPDATE neighbor_snr_aggregate_collections SET records=records+?,session=?,diagnostics=?,warning=? WHERE poll_id=?',
                    (int(item is not None),header['session'],json.dumps(diagnostics),warning,poll_id))
        return True


def finish_for(path,key,poll_id,complete,error='',warning=''):
    target=passive_stats.statistics_path(path,key)
    if not target.exists():return
    with closing(sqlite3.connect(target,timeout=.25)) as db,db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_snr_aggregate_collections'").fetchone():
            db.execute('UPDATE neighbor_snr_aggregate_collections SET finished_at=?,complete=?,error=?,warning=? WHERE poll_id=?',
                (time.time(),int(complete),error[:300],warning[:1000],poll_id))


def recover_collection(path,key):
    target=passive_stats.statistics_path(path,key)
    if not target.exists():return
    with closing(sqlite3.connect(target,timeout=.25)) as db,db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_snr_aggregate_collections'").fetchone():
            db.execute("UPDATE neighbor_snr_aggregate_collections SET finished_at=?,error='Collection interrupted; evidence and cursor preserved.' WHERE finished_at IS NULL",(time.time(),))


def summary(source,registry,start,end):
    quality=dict(invalid_utc_records=0,discontinuous_records=0,boundary_windows=0,partial_collections=0,sequence_gaps=0,reported_loss=False)
    if not source.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_snr_aggregates'").fetchone():return [],quality
    values=source.execute('''SELECT neighbor_key,SUM(snr_sum),SUM(sample_count),MIN(minimum),MAX(maximum),MAX(last_utc),COUNT(*),MAX(flags&4)
      FROM neighbor_snr_aggregates WHERE utc_start>=? AND utc_start<? AND utc_end<=? AND (flags&3)=1 GROUP BY neighbor_key''',(start,end,end))
    rows=[dict(public_key=key,prefix=key,resolution='matched',name=registry.get(key,{}).get('name'),average_snr=total/(4*count),samples=count,
        minimum_snr=minimum/4,maximum_snr=maximum/4,last_heard=last,windows=windows,source='firmware_aggregates',sample_overflow=bool(overflow))
        for key,total,count,minimum,maximum,last,windows,overflow in values]
    quality['invalid_utc_records'],quality['discontinuous_records']=source.execute('SELECT COUNT(*),COALESCE(SUM((flags&2)!=0),0) FROM neighbor_snr_aggregates WHERE utc_start IS NULL').fetchone()
    quality['boundary_windows']=source.execute('SELECT COUNT(*) FROM neighbor_snr_aggregates WHERE utc_start>=? AND utc_end>? AND utc_start<? AND (utc_start<? OR utc_end>?)',(start-1800,start,end,start,end)).fetchone()[0]
    quality['partial_collections']=source.execute('SELECT COUNT(*) FROM neighbor_snr_aggregate_collections WHERE started_at>=? AND started_at<? AND complete=0',(start,end)).fetchone()[0]
    quality['sequence_gaps']=source.execute('SELECT COUNT(*) FROM neighbor_snr_sequence_gaps WHERE noticed_at>=? AND noticed_at<?',(start,end)).fetchone()[0]
    last=source.execute('SELECT diagnostics FROM neighbor_snr_aggregate_collections ORDER BY started_at DESC LIMIT 1').fetchone()
    counters=json.loads(last[0]) if last else {}
    quality['reported_loss']=any(counters.get(k,0) for k in ('expired','evicted','dropped'))
    return rows,quality
