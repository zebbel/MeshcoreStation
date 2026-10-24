"""Local performance journal and bounded analyzer measurements. Never uses a radio."""
from contextlib import contextmanager, closing
import json
from datetime import datetime
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
        CREATE TABLE IF NOT EXISTS lifecycle (
          public_key TEXT PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0,
          deleted INTEGER NOT NULL DEFAULT 0, min_at REAL NOT NULL DEFAULT 0);
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
        CREATE TABLE IF NOT EXISTS hourly_relays (
          public_key TEXT NOT NULL, at INTEGER NOT NULL, count INTEGER NOT NULL,
          retrieved_at REAL NOT NULL, PRIMARY KEY(public_key,at));
        CREATE INDEX IF NOT EXISTS performance_hour_at ON hourly_relays(at);
        CREATE TABLE IF NOT EXISTS measurement_details (
          public_key TEXT NOT NULL, at REAL NOT NULL, pairs REAL, routes INTEGER,
          betweenness REAL, graph_rank REAL, PRIMARY KEY(public_key,at));
        CREATE TABLE IF NOT EXISTS collection_schedule (
          public_key TEXT PRIMARY KEY, next_at REAL NOT NULL DEFAULT 0,
          attempted_at REAL, success_at REAL, state TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS collection_control (
          id INTEGER PRIMARY KEY CHECK(id=1), next_at REAL NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO collection_control(id) VALUES(1);
        CREATE INDEX IF NOT EXISTS performance_marker_key ON markers(public_key,at);
        ''')
        with db:
            yield db
    finally:
        db.close()


def lifecycle(db, key):
    # Start a writer transaction before checking a removal tombstone. This
    # serializes late cache/audit/annotation writes with managed-repeater removal.
    db.execute('INSERT OR IGNORE INTO lifecycle(public_key) VALUES(?)', (key,))
    return dict(db.execute('SELECT * FROM lifecycle WHERE public_key=?', (key,)).fetchone())


def allow_repeater(key):
    with database() as db:
        lifecycle(db,key)
        db.execute('UPDATE lifecycle SET deleted=0,min_at=? WHERE public_key=? AND deleted=1', (time.time(),key))


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
        state=lifecycle(db,key)
        if state['deleted'] or at<state['min_at']:
            return
        db.execute('INSERT OR IGNORE INTO measurements VALUES(?,?,?,?,?,?,?,?)',
          (key, int(at * 1000000), at, number(stat.get('relayCount1h')), number(stat.get('relayCount24h')),
           len(peers) if roles_known else None, sum(bidirectional(p) for p in peers.values()) if roles_known else None, number(data['metrics'].get('degree'))))
        db.execute('INSERT OR IGNORE INTO measurement_details VALUES(?,?,?,?,?,?)',
          (key,at,number(stat.get('pairsServed')),len(data['detail']['pathsThroughNode']),
           number(data['metrics'].get('betweenness')),number(data['metrics'].get('rank'))))
        for row in data['detail'].get('relayTimeline',[]):
            # Only complete, explicitly returned hourly buckets. Absent hours are
            # unknown, never inferred zero. UTC offset required; preserve instant.
            try:
                stamp=datetime.fromisoformat(row['bucket'].replace('Z','+00:00'))
                hour=stamp.timestamp()
                count=row['count']
                if stamp.tzinfo is None or hour%3600 or type(count) is not int or count<0:
                    continue
                if not max(at-RETENTION,state['min_at'])<=hour or hour+3600>at:
                    continue
            except (KeyError,ValueError,TypeError,OverflowError,AttributeError):
                continue
            db.execute('''INSERT INTO hourly_relays VALUES(?,?,?,?)
              ON CONFLICT(public_key,at) DO UPDATE SET count=excluded.count,retrieved_at=excluded.retrieved_at
              WHERE excluded.retrieved_at>hourly_relays.retrieved_at''', (key,int(hour),count,at))
        prune(db,at)



def prune(db, now):
    for table in ('measurements','hourly_relays','measurement_details'):
        db.execute(f'DELETE FROM {table} WHERE at<?',(now-RETENTION,))
        db.execute(f'DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} ORDER BY at DESC LIMIT -1 OFFSET ?)',(MAX_SAMPLES,))


def hourly(key,start,end):
    with database() as db:
        return [dict(r) for r in db.execute('SELECT * FROM hourly_relays WHERE public_key=? AND at>=? AND at+3600<=? ORDER BY at',(key,start,end))]


def collection_status(key):
    with database() as db:
        row=db.execute('SELECT * FROM collection_schedule WHERE public_key=?',(key,)).fetchone()
        return dict(row) if row else None


def performance_summary(key,start,now,local,latest):
    rows=hourly(key,start,now)
    first_hour=math.ceil(start/3600)*3600
    end_hour=int(now//3600)*3600
    expected=max(0,int((end_hour-first_hour)//3600))
    # Compare equally sized completed hourly halves, with complete evidence only.
    half=expected//2
    split=end_hour-half*3600
    selected=[r for r in rows if end_hour-2*half*3600<=r['at']<end_hour]
    before=[r['count'] for r in selected if r['at']<split]
    after=[r['count'] for r in selected if r['at']>=split]
    reliable=half>0 and len(before)==half and len(after)==half
    trend='Not enough complete history to assess a trend.'
    percent=None
    if reliable:
        b,a=sum(before),sum(after)
        if a==b: trend='Observed hourly forwarding was unchanged between equal periods.'
        elif b:
            percent=100*(a-b)/b
            trend=f"Observed hourly forwarding was {abs(percent):.1f}% {'higher' if a>b else 'lower'} in the recent half of this period."
        else: trend='Forwarding was observed after a recorded zero baseline; a percentage is unavailable.'
    latest_hour=rows[-1] if rows else None
    fresh=latest and 0<=now-latest['at']<=13*3600
    activity=('Forwarding observed' if latest_hour['count']>0 else 'No forwarding in latest recorded hour') if latest_hour and now-latest_hour['at']<=13*3600 else 'No recent hourly evidence'
    with database() as db:
        details=db.execute('SELECT * FROM measurement_details WHERE public_key=? AND at<=? ORDER BY at DESC LIMIT 1',(key,now)).fetchone()
    share=100*local['copies']/local['network'] if local.get('copies') is not None and local.get('network') and local.get('source','').startswith('Optimization Analysis') else None
    context='Companion network observations provide separate context; their reception coverage is not a measure of total mesh traffic.'
    if reliable:
        network_before=passive(key,end_hour-2*half*3600,split,3600).get('network')
        network_after=passive(key,split,end_hour,3600).get('network')
        if network_before and network_after is not None:
            pct=100*(network_after-network_before)/network_before
            context=f"Over the same periods, Companion received network traffic was {abs(pct):.1f}% {'higher' if pct>=0 else 'lower'}. Different source coverage prevents attributing this difference to the repeater."
    return {'activity':activity,'trend':trend,'trend_complete':reliable,'trend_percent':percent,
        'hourly_observed':len(rows),'hourly_expected':expected,'hourly_total':sum(r['count'] for r in rows) if rows else None,
        'first_hour':rows[0]['at'] if rows else None,'last_hour':latest_hour['at'] if rows else None,
        'network_context':context,'snapshot_recent':bool(fresh),'companion_share':share,'details':dict(details) if details else None,
        'collection':collection_status(key),
        'explanation':'Higher activity is not automatically better performance. Network traffic, observer coverage and routing can change; these observations do not prove delivery success.'}

def import_verified(rows, path=None):
    with database(path) as db:
        for r in rows:
            if r.get('status') != 'verified' or r.get('actual') is None or r.get('actual') != r.get('requested'):
                continue
            state=lifecycle(db,r['public_key'])
            if state['deleted'] or r['at']<state['min_at']:
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
        state=lifecycle(db,key)
        revision=data.get('revision',0)
        if type(revision) is not int or state['deleted'] or revision!=state['generation']:
            raise ValueError('Repeater management changed. Reopen Repeater Performance before saving.')
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
        lifecycle(db,key)
        db.execute('UPDATE lifecycle SET deleted=1,generation=generation+1 WHERE public_key=?', (key,))
        db.execute('DELETE FROM measurements WHERE public_key=?', (key,))
        db.execute('DELETE FROM markers WHERE public_key=?', (key,))
        for table in ('hourly_relays','measurement_details','collection_schedule'):
            db.execute(f'DELETE FROM {table} WHERE public_key=?', (key,))


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
        hours=hourly(key,start,min(stop,now))
        expected=max(0,int(math.floor(stop/3600)-math.ceil(start/3600)))
        reach_hours={int(r['at']//3600):r for r in measurements(key,start,min(stop,now))}
        def mean(field):
            source=samples if field=='relay_1h' else reach_hours.values()
            values = [r[field] for r in source if r[field] is not None]
            return sum(values)/len(values) if values else None
        with database() as db:
            detail_rows=[dict(r) for r in db.execute('SELECT * FROM measurement_details WHERE public_key=? AND at>=? AND at<? ORDER BY at',(key,start,min(stop,now)))]
        detail_hours={int(r['at']//3600):r for r in detail_rows}
        def detail_mean(field):
            values=[r[field] for r in detail_hours.values() if r[field] is not None]
            return sum(values)/len(values) if values else None
        neighbor_readings={int(r['at']//3600):r['observed'] for r in optimizer_samples(key,start,min(stop,now))}
        result['windows'][name] = {'start':start,'end':stop,'observed_until':min(stop,now),
            'values':{'companion_packets':p['copies'],'distinct_packets':p['unique'],'observed_routes':p['routes'],
                      'companion_network_packets':p['network'],'analyzer_hourly_relays_mean':sum(r['count'] for r in hours)/len(hours) if hours else mean('relay_1h'),
                      'analyzer_neighbors_mean':mean('neighbors'),'analyzer_bidirectional_mean':mean('two_way'),
                      'analyzer_pairs_mean':detail_mean('pairs'),'analyzer_routes_mean':detail_mean('routes'),
                      'optimizer_neighbors_mean':sum(neighbor_readings.values())/len(neighbor_readings) if neighbor_readings else None},
            'optimizer_samples':len(neighbor_readings),
            'analyzer_samples':len(hours) if hours else len(samples),'analyzer_source':'Original hourly buckets' if hours else 'Legacy rolling 1h samples','expected_hourly_samples':expected,'analyzer_snapshot_samples':len(reach_hours),
            'companion_source':p.get('source','No saved Companion observations'),
            'companion_buckets_with_packets':sum(b['copies'] is not None for b in p['bins']),
            'first_companion':p['first'],'last_companion':p['last']}
        if stop>now:
            result['warnings'].append(f'{name.title()} window is incomplete; observations are still being collected.')
        if p.get('error'):
            result['warnings'].append(p['error'])
        if p['first'] is None or p['first']>start+3600 or p['last']<min(stop,now)-3600:
            result['warnings'].append(f'{name.title()} Companion observations do not span the full window.')
        if (len(hours) if hours else len(samples))<expected:
            result['warnings'].append(f'{name.title()} analyzer coverage is incomplete ({len(hours) if hours else len(samples)}/{expected} complete hourly samples).')
        if p.get('trimmed_at') and p['trimmed_at']>=start:
            result['warnings'].append(f'{name.title()} Companion history may have been trimmed.')
    before,after = (result['windows'][n]['values'] for n in ('before','after'))
    collecting=any(w['end']>now for w in result['windows'].values())
    for field,b in before.items():
        a = after[field]
        result['differences'][field] = {'before':b,'after':a,'absolute':a-b if a is not None and b is not None else None,
            'percent':100*(a-b)/b if not collecting and a is not None and b is not None and b!=0 else None,
            'reason':'Window still collecting' if collecting else 'Missing observations' if a is None or b is None else 'Zero baseline' if b==0 else None}
        if field=='analyzer_hourly_relays_mean' and any(w['analyzer_samples']<w['expected_hourly_samples'] for w in result['windows'].values()):
            result['differences'][field].update(percent=None,reason='Incomplete hourly observations')
    overlap = [m['id'] for m in all_markers if m['id']!=marker['id'] and marker['at']-width<=m['at']<marker['at']+width]
    if overlap:
        result['warnings'].append(f'{len(overlap)} other logged changes overlap these windows.')
    if result['windows']['before']['companion_source'] != result['windows']['after']['companion_source']:
        result['warnings'].append('The Companion source differs between windows; differences may reflect collection scope rather than performance.')
    result['warnings'].append('Companion uptime and reception completeness were not historically recorded. Missing records are not proof of zero activity. Percentages are unavailable for missing or zero baselines.')
    result['overlapping_markers'] = overlap
    for field,label in (() if collecting else (('companion_packets','Companion path packet count'),('analyzer_hourly_relays_mean','mean Analyzer hourly relay count'))):
        change=result['differences'][field]
        if change['before'] is None or change['after'] is None:
            continue
        if change['absolute']==0:
            text=f'The recorded {label} was unchanged.'
        elif change['percent'] is None:
            text=f'The recorded {label} differs, but a percentage is unavailable ({change["reason"]}).'
        else:
            text=f"The recorded {label} was {abs(change['percent']):.1f}% {'higher' if change['percent']>0 else 'lower'} in the after window."
        result['interpretation']=text+' Coverage is incomplete or uncertain; this is an activity difference, not a delivery-success rate. '+result['interpretation']
        break
    else:
        result['interpretation']=('The equal after-window is still collecting; full-window percentage comparisons are not yet available. ' if collecting else 'Insufficient paired observations for an activity comparison. ')+result['interpretation']
    return result


def overview(key, days, now=None, marker_id=None, compare_days=7):
    now = time.time() if now is None else now
    with database() as db:
        state=lifecycle(db,key)
        if state['deleted']:
            raise ValueError('This repeater was removed from management.')
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
        prune(db,now)
        latest = db.execute('SELECT * FROM measurements WHERE public_key=? AND at<=? ORDER BY at DESC LIMIT 1', (key,now)).fetchone()
        latest = dict(latest) if latest else None
    for reading in optimizer_samples(key,start,now):
        at=int(reading['at']//step)*step
        if at in bins:
            bins[at]['optimizer_neighbors']=reading['observed']
            bins[at]['optimizer_at']=reading['at']
    # Hourly series is distinct from rolling snapshot totals. Bucket aggregates
    # contain only explicitly observed hours; never bridge absent hours.
    hour_rows=hourly(key,start,now)
    for b in bins.values():
        h=[r for r in hour_rows if b['at']<=r['at']<b['at']+step]
        b['hourly_relays']=sum(r['count'] for r in h)/len(h) if h else None
        b['hourly_count']=len(h)
        b['hourly_at']=h[-1]['at'] if h else None
    neighbor = optimizer_neighbors(key,now)
    result = {'ok':True,'public_key':key,'revision':state['generation'],'days':days,'now':now,'start':start,'step':step,
              'local':{k:v for k,v in local.items() if k!='bins'},'analyzer':latest,'optimizer_neighbors':neighbor,
              'timeline':list(bins.values()),'markers':journal,
              'summary':performance_summary(key,start,now,local,latest),
              'hourly_timeline':[{'at':h,'hourly_at':h,'hourly_relays':next((r['count'] for r in hour_rows if r['at']==h),None)} for h in range(math.ceil(start/3600)*3600,int(now//3600)*3600,3600)],
              'analyzer_buckets':sum(b['analyzer_at'] is not None for b in bins.values()),
              'notes':['Companion values are received packet copies with this repeater in a collision-checked path, not proven direct forwarding or delivery success.',
                       'Analyzer forwarding charts preserve original complete hourly buckets at every selected period length. Reach is the latest snapshot per display interval. Missing hours remain unknown; rolling totals are never added.',
                       'Observations from different sources are shown separately, never added into a performance score.']}
    if marker_id is not None:
        marker = next((m for m in journal if m['id']==marker_id),None)
        if not marker:
            raise ValueError('Change marker not found for this repeater.')
        result['comparison']=comparison(key,marker,compare_days,now,journal)
    return result
