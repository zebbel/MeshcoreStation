"""Local performance journal and bounded analyzer measurements. Never uses a radio."""
from contextlib import contextmanager, closing
import json
import math
import sqlite3
import time
from meshcorestation.config import DATA_DIR
from meshcorestation.storage import passive_stats, optimizer_store, advisor_history

FILE = DATA_DIR / 'repeater-performance.db'
DAY = 86400
RETENTION = 400 * DAY
MAX_SAMPLES = 250000


@contextmanager
def database(path=None):
    path = path or FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS measurements (
          public_key TEXT NOT NULL, bucket INTEGER NOT NULL, at REAL NOT NULL,
          relay_1h REAL, relay_24h REAL, neighbors INTEGER, two_way INTEGER, degree REAL,
          PRIMARY KEY(public_key,bucket));
        CREATE INDEX IF NOT EXISTS performance_measurement_at ON measurements(at);
        CREATE UNIQUE INDEX IF NOT EXISTS performance_measurement_instant ON measurements(public_key,at);
        CREATE TABLE IF NOT EXISTS markers (
          id INTEGER PRIMARY KEY AUTOINCREMENT, public_key TEXT NOT NULL, at REAL NOT NULL,
          description TEXT NOT NULL, source_id TEXT UNIQUE, source_at REAL,
          provenance TEXT, deleted INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS performance_marker_key ON markers(public_key,at);
        ''')
        with db:
            yield db
    finally:
        db.close()


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def record_analyzer(key, at, data, path=None):
    """Keep each fresh retrieval; exact cached timestamps deduplicate. Never sum rolling counts."""
    peers = [r for r in data['reach']['neighbourList'] if isinstance(r.get('role'),str) and r['role'].lower() == 'repeater']
    peers = {r.get('pubkey'): r for r in peers if r.get('pubkey')}
    def bidirectional(n):
        we, they = number(n.get('weHear')), number(n.get('theyHear'))
        return (we is not None and they is not None and we > 0 and they > 0) or (n.get('twoWay') is True and we != 0 and they != 0)
    roles_known=all(isinstance(n.get('role'),str) and n['role'].strip() for n in data['reach']['neighbourList'])
    stat = data['detail']['stat']
    with database(path) as db:
        db.execute('INSERT OR IGNORE INTO measurements VALUES(?,?,?,?,?,?,?,?)',
          (key, int(at * 1000000), at, number(stat.get('relayCount1h')), number(stat.get('relayCount24h')),
           len(peers) if roles_known else None, sum(bidirectional(p) for p in peers.values()) if roles_known else None, number(data['metrics'].get('degree'))))
        db.execute('DELETE FROM measurements WHERE at<?', (at-RETENTION,))
        db.execute('''DELETE FROM measurements WHERE rowid IN
          (SELECT rowid FROM measurements ORDER BY at DESC LIMIT -1 OFFSET ?)''', (MAX_SAMPLES,))


def import_verified(rows, path=None):
    with database(path) as db:
        for r in rows:
            if r.get('status') != 'verified' or r.get('actual') is None or r.get('actual') != r.get('requested'):
                continue
            description = f"Verified {r['field']}: {r.get('before_value')} → {r['actual']}"
            db.execute('''INSERT OR IGNORE INTO markers
              (public_key,at,description,source_id,source_at,provenance) VALUES(?,?,?,?,?,?)''',
              (r['public_key'], r['at'], description[:500], str(r['id']), r['at'],
               json.dumps({k:r.get(k) for k in ('field','before_value','requested','actual','status')})))


def sync_verified(key):
    if advisor_history.FILE.exists():
        with advisor_history.database() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM changes WHERE public_key=? AND status='verified'", (key,))]
        import_verified(rows)


def markers(key):
    with database() as db:
        return [dict(r) for r in db.execute('SELECT * FROM markers WHERE public_key=? AND deleted=0 ORDER BY at DESC,id DESC', (key,))]


def marker_change(key, action, data, now=None):
    now = time.time() if now is None else now
    ident = data.get('id')
    if action != 'create' and (type(ident) is not int or ident <= 0):
        raise ValueError('Choose a valid change marker.')
    if action != 'delete':
        text, at = data.get('description'), data.get('at', now)
        if not isinstance(text,str) or not text.strip() or len(text.strip()) > 500:
            raise ValueError('Describe the change using 1–500 characters.')
        if type(at) not in (int,float) or not math.isfinite(at) or not 0 <= at <= now+60:
            raise ValueError('Choose a valid date/time, not a future date.')
    with database() as db:
        if action == 'create':
            ident = db.execute('INSERT INTO markers(public_key,at,description) VALUES(?,?,?)', (key,at,text.strip())).lastrowid
        elif action in ('edit','delete'):
            if not db.execute('SELECT 1 FROM markers WHERE public_key=? AND id=? AND deleted=0', (key,ident)).fetchone():
                raise ValueError('Change marker not found for this repeater.')
            if action == 'delete':
                # A tombstone prevents verified history backfill resurrecting deletions.
                db.execute("UPDATE markers SET deleted=1,description='',at=0,source_at=NULL,provenance=NULL WHERE id=?", (ident,))
            else:
                db.execute('UPDATE markers SET description=?,at=? WHERE id=?', (text.strip(),at,ident))
        else:
            raise ValueError('Unknown change-marker action.')
    return ident


def remove_repeater(key, path=None):
    with database(path) as db:
        db.execute('DELETE FROM measurements WHERE public_key=?', (key,))
        db.execute('DELETE FROM markers WHERE public_key=?', (key,))


def measurements(key, start, end):
    with database() as db:
        return [dict(r) for r in db.execute('SELECT * FROM measurements WHERE public_key=? AND at>=? AND at<? ORDER BY at', (key,start,end))]


def passive(key, start, end, step):
    """Reuse Optimization Analysis's hash-width/collision policy, with exact windows.

    No packets in a bucket means unknown, not a proven zero-traffic interval.
    No raw packet bodies or routes are copied into the new database.
    """
    bins = {at:{'at':at,'copies':None,'network':None,'ambiguous':None} for at in range(int(start//step)*step, int((end-0.000001)//step)*step+1, step)}
    empty = {'copies':None,'unique':None,'routes':None,'network':None,'ambiguous':None,'first':None,'last':None,'bins':list(bins.values()),'error':None,'source':'No saved Companion observations'}
    if not passive_stats.STATS_PATH.exists():
        return empty
    try:
        keys = {r['public_key'] for r in passive_stats.known_repeaters()} | {key}
        good, bad = [], []
        for size in (1,2,3):
            target = bad if sum(k.startswith(key[:size*2]) for k in keys)>1 else good
            target.append((size, '%|'+key[:size*2]+'|%'))
        def predicate(parts):
            return ' OR '.join("(hash_size=? AND ('|'||route||'|') LIKE ?)" for _ in parts) or '0'
        def args(parts):
            return [v for pair in parts for v in pair]
        with closing(passive_stats.connect()) as db:
            db.execute('BEGIN')
            health = db.execute('SELECT * FROM health WHERE id=1').fetchone()
            total = db.execute('SELECT COUNT(*),MIN(at),MAX(at) FROM network_observations WHERE at>=? AND at<?', (start,end)).fetchone()
            row = db.execute(f'SELECT COUNT(*),COUNT(DISTINCT digest),COUNT(DISTINCT route) FROM network_observations WHERE at>=? AND at<? AND ({predicate(good)})', (start,end,*args(good))).fetchone()
            uncertain = db.execute(f'SELECT COUNT(*) FROM network_observations WHERE at>=? AND at<? AND ({predicate(bad)})', (start,end,*args(bad))).fetchone()[0]
            for bucket,n in db.execute('SELECT CAST(at/? AS INTEGER)*?,COUNT(*) FROM network_observations WHERE at>=? AND at<? GROUP BY 1', (step,step,start,end)):
                bins[bucket].update(network=n,copies=0,ambiguous=0)
            for parts,field in ((good,'copies'),(bad,'ambiguous')):
                for bucket,n in db.execute(f'SELECT CAST(at/? AS INTEGER)*?,COUNT(*) FROM network_observations WHERE at>=? AND at<? AND ({predicate(parts)}) GROUP BY 1', (step,step,start,end,*args(parts))):
                    bins[bucket][field] = n
            # Prefer the managed repeater's Statistics stream, which remains
            # available when the separate local Optimizer is disabled. Never add
            # these packet copies to the same packets in network_observations.
            tracked=db.execute('SELECT COUNT(*),MIN(at),MAX(at) FROM observations WHERE target=? AND at>=? AND at<?', (key,start,end)).fetchone()
            source='Optimization Analysis path observations'
            available=bool(total[0])
            first,last=total[1],total[2]
            if tracked[0]:
                source='Repeater Statistics path observations';available=True;first,last=tracked[1],tracked[2]
                row=db.execute("SELECT COUNT(*),COUNT(DISTINCT digest),COUNT(DISTINCT (SELECT group_concat(json_extract(j.value,'$.key'),'|') FROM json_each(o.route) j)) FROM observations o WHERE target=? AND at>=? AND at<? AND ambiguous=0", (key,start,end)).fetchone()
                uncertain=db.execute('SELECT COUNT(*) FROM observations WHERE target=? AND at>=? AND at<? AND ambiguous=1', (key,start,end)).fetchone()[0]
                for b in bins.values(): b['copies']=0 if b['network'] is not None else None;b['ambiguous']=0 if b['network'] is not None else None
                for bucket,n,ambiguous in db.execute('SELECT CAST(at/? AS INTEGER)*?,SUM(ambiguous=0),SUM(ambiguous=1) FROM observations WHERE target=? AND at>=? AND at<? GROUP BY 1', (step,step,key,start,end)):
                    bins[bucket].update(copies=n,ambiguous=ambiguous)
        return {'copies':row[0] if available else None,'unique':row[1] if available else None,

                'routes':row[2] if available else None,'network':total[0] or None,'ambiguous':uncertain if available else None,
                'first':first,'last':last,'bins':list(bins.values()),'source':source,
                'error':(health['error'] if health else '') or passive_stats.collector.error,
                'trimmed_at':health['trimmed_at'] if health else None}
    except (OSError,sqlite3.Error):
        return {**empty,'error':'Companion history unavailable. Check local statistics storage.'}


def optimizer_samples(key, start, end):
    if not optimizer_store.FILE.exists():
        return []
    try:
        with closing(optimizer_store.connect()) as db:
            return [dict(r) for r in db.execute('''SELECT s.at,s.complete,COUNT(DISTINCT n.neighbor_key) observed
                FROM snapshots s LEFT JOIN neighbors n ON n.snapshot_id=s.id
                WHERE s.public_key=? AND s.at>=? AND s.at<? GROUP BY s.id ORDER BY s.at''', (key,start,end))]
    except (OSError,sqlite3.Error):
        return []


def optimizer_neighbors(key, end):
    if not optimizer_store.FILE.exists():
        return None
    try:
        with closing(optimizer_store.connect()) as db:
            row = db.execute('SELECT id,at,reported,complete FROM snapshots WHERE public_key=? AND at<=? ORDER BY at DESC LIMIT 1', (key,end)).fetchone()
            if row:
                return {**dict(row),'observed':db.execute('SELECT COUNT(DISTINCT neighbor_key) FROM neighbors WHERE snapshot_id=?', (row['id'],)).fetchone()[0]}
    except (OSError,sqlite3.Error):
        pass
    return None


def comparison(key, marker, days, now, all_markers):
    width = days*DAY
    periods = [('before',marker['at']-width,marker['at']),('after',marker['at'],marker['at']+width)]
    result = {'days':days,'windows':{},'differences':{},'warnings':[],
              'interpretation':'Measured differences describe observations only. Correlation does not prove that this change caused an improvement; observer coverage and traffic mix can change.'}
    for name,start,stop in periods:
        p = passive(key,start,min(stop,now),3600) if start < now else {'copies':None,'routes':None,'unique':None,'network':None,'first':None,'last':None,'bins':[],'source':'No saved Companion observations'}
        # Keep only fully-contained, non-overlapping rolling 1h samples.
        samples = []
        for row in measurements(key,start, min(stop,now)+0.000001):
            if row['at']-3600 >= start and (not samples or row['at']-samples[-1]['at'] >= 3600):
                samples.append(row)
        def mean(field):
            values = [r[field] for r in samples if r[field] is not None]
            return sum(values)/len(values) if values else None
        neighbor_readings={int(r['at']//3600):r['observed'] for r in optimizer_samples(key,start,min(stop,now))}
        result['windows'][name] = {'start':start,'end':stop,'observed_until':min(stop,now),
            'values':{'companion_packets':p['copies'],'distinct_packets':p['unique'],'observed_routes':p['routes'],
                      'companion_network_packets':p['network'],'analyzer_hourly_relays_mean':mean('relay_1h'),
                      'analyzer_neighbors_mean':mean('neighbors'),'analyzer_bidirectional_mean':mean('two_way'),
                      'optimizer_neighbors_mean':sum(neighbor_readings.values())/len(neighbor_readings) if neighbor_readings else None},
            'optimizer_samples':len(neighbor_readings),
            'analyzer_samples':len(samples),'expected_hourly_samples':int(width//3600),
            'companion_source':p.get('source','No saved Companion observations'),
            'companion_buckets_with_packets':sum(b['copies'] is not None for b in p['bins']),
            'first_companion':p['first'],'last_companion':p['last']}
        if stop>now:
            result['warnings'].append(f'{name.title()} window is incomplete; observations are still being collected.')
        if p.get('error'):
            result['warnings'].append(p['error'])
        if p['first'] is None or p['first']>start+3600 or p['last']<min(stop,now)-3600:
            result['warnings'].append(f'{name.title()} Companion observations do not span the full window.')
        if len(samples)<int(width//3600):
            result['warnings'].append(f'{name.title()} analyzer coverage is incomplete ({len(samples)}/{int(width//3600)} non-overlapping hourly samples).')
        if p.get('trimmed_at') and p['trimmed_at']>=start:
            result['warnings'].append(f'{name.title()} Companion history may have been trimmed.')
    before,after = (result['windows'][n]['values'] for n in ('before','after'))
    collecting=any(w['end']>now for w in result['windows'].values())
    for field,b in before.items():
        a = after[field]
        result['differences'][field] = {'before':b,'after':a,'absolute':a-b if a is not None and b is not None else None,
            'percent':100*(a-b)/b if not collecting and a is not None and b is not None and b!=0 else None,
            'reason':'Window still collecting' if collecting else 'Missing observations' if a is None or b is None else 'Zero baseline' if b==0 else None}
    overlap = [m['id'] for m in all_markers if m['id']!=marker['id'] and marker['at']-width<=m['at']<marker['at']+width]
    if overlap:
        result['warnings'].append(f'{len(overlap)} other logged changes overlap these windows.')
    if result['windows']['before']['companion_source'] != result['windows']['after']['companion_source']:
        result['warnings'].append('The Companion source differs between windows; differences may reflect collection scope rather than performance.')
    result['warnings'].append('Companion uptime and reception completeness were not historically recorded. Missing records are not proof of zero activity. Percentages are unavailable for missing or zero baselines.')
    result['overlapping_markers'] = overlap
    for field,label in (() if collecting else (('companion_packets','Companion path packet count'),('analyzer_hourly_relays_mean','mean analyzer rolling 1h relay count'))):
        change=result['differences'][field]
        if change['before'] is None or change['after'] is None:
            continue
        if change['absolute']==0:
            text=f'The recorded {label} was unchanged.'
        elif change['percent'] is None:
            text=f'The recorded {label} increased from a zero baseline; a percentage is unavailable.'
        else:
            text=f"The recorded {label} was {abs(change['percent']):.1f}% {'higher' if change['percent']>0 else 'lower'} in the after window."
        result['interpretation']=text+' Coverage is incomplete or uncertain; this is an activity difference, not a delivery-success rate. '+result['interpretation']
        break
    else:
        result['interpretation']=('The equal after-window is still collecting; full-window percentage comparisons are not yet available. ' if collecting else 'Insufficient paired observations for an activity comparison. ')+result['interpretation']
    return result


def overview(key, days, now=None, marker_id=None, compare_days=7):
    now = time.time() if now is None else now
    sync_verified(key)
    journal = markers(key)
    start = now-days*DAY
    step = 3600 if days==1 else 21600 if days==7 else DAY
    local = passive(key,start,now,step)
    archive = measurements(key,start,now+0.000001)
    bins = {b['at']:{**b,'relay_1h':None,'relay_24h':None,'neighbors':None,'two_way':None,'analyzer_at':None,'optimizer_neighbors':None,'optimizer_at':None} for b in local['bins']}
    for r in archive:
        at = int(r['at']//step)*step
        if at in bins:
            bins[at].update({f:r[f] for f in ('relay_1h','relay_24h','neighbors','two_way')})
            bins[at]['analyzer_at']=r['at']
    with database() as db:
        db.execute('DELETE FROM measurements WHERE at<?', (now-RETENTION,))
        latest = db.execute('SELECT * FROM measurements WHERE public_key=? AND at<=? ORDER BY at DESC LIMIT 1', (key,now)).fetchone()
        latest = dict(latest) if latest else None
    for reading in optimizer_samples(key,start,now):
        at=int(reading['at']//step)*step
        if at in bins:
            bins[at]['optimizer_neighbors']=reading['observed']
            bins[at]['optimizer_at']=reading['at']
    neighbor = optimizer_neighbors(key,now)
    result = {'ok':True,'public_key':key,'days':days,'now':now,'start':start,'step':step,
              'local':{k:v for k,v in local.items() if k!='bins'},'analyzer':latest,'optimizer_neighbors':neighbor,
              'timeline':list(bins.values()),'markers':journal,
              'analyzer_buckets':sum(b['analyzer_at'] is not None for b in bins.values()),
              'notes':['Companion values are received packet copies with this repeater in a collision-checked path, not proven direct forwarding or delivery success.',
                       'Analyzer chart points are the latest saved measurement per bucket; rolling counts are not added. Blank intervals are collection gaps.',
                       'Observations from different sources are shown separately, never added into a performance score.']}
    if marker_id is not None:
        marker = next((m for m in journal if m['id']==marker_id),None)
        if not marker:
            raise ValueError('Change marker not found for this repeater.')
        result['comparison']=comparison(key,marker,compare_days,now,journal)
    return result
