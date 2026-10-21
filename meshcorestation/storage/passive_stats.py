"""Passive, selected-repeater observations. No radio commands or payload storage."""
from contextlib import closing
import hashlib
import json
import logging
import queue
import os
import shutil
import re
import sqlite3
import threading
import time
from meshcorestation.config import DATA_DIR, DB_PATH

STATS_PATH = DATA_DIR / 'repeater-statistics.db'
RETENTION = 60 * 86400
SUMMARY_RETENTION = 365 * 86400
KINDS = {0:'Request',1:'Response',2:'Direct text',3:'ACK',4:'Advertisement',5:'Group text',6:'Group data',7:'Anonymous request',8:'Path',9:'Trace',10:'Multipart',11:'Control'}


def connect():
    db = sqlite3.connect(STATS_PATH, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def initialize():
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as db, db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS selection (id INTEGER PRIMARY KEY CHECK(id=1), public_key TEXT NOT NULL, since REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS subscriptions (public_key TEXT PRIMARY KEY, since REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY, target TEXT NOT NULL, at REAL NOT NULL, digest TEXT,
                kind INTEGER NOT NULL, scoped INTEGER NOT NULL, ambiguous INTEGER NOT NULL,
                first_hop INTEGER NOT NULL, middle_hop INTEGER NOT NULL, last_hop INTEGER NOT NULL,
                route TEXT NOT NULL, previous TEXT NOT NULL, following TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS observations_target_at ON observations(target, at);
            CREATE INDEX IF NOT EXISTS observations_at ON observations(at);
            CREATE TABLE IF NOT EXISTS network_observations(
              id INTEGER PRIMARY KEY, at REAL NOT NULL, kind INTEGER NOT NULL,
              scoped INTEGER NOT NULL, path_len INTEGER NOT NULL, hash_size INTEGER NOT NULL,
              route TEXT NOT NULL, digest TEXT, rssi REAL, snr REAL);
            CREATE INDEX IF NOT EXISTS network_at ON network_observations(at);
            CREATE TABLE IF NOT EXISTS network_daily (
              day INTEGER NOT NULL, kind INTEGER NOT NULL, scoped INTEGER NOT NULL,
              copies INTEGER NOT NULL, PRIMARY KEY(day,kind,scoped));
            CREATE TABLE IF NOT EXISTS health (id INTEGER PRIMARY KEY CHECK(id=1), heartbeat REAL, dropped INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', trimmed_at REAL);
            INSERT OR IGNORE INTO health(id) VALUES(1);
        ''')


def known_repeaters():
    try:
        with closing(sqlite3.connect(DB_PATH.as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
            return [{'public_key':r[0].lower(),'name':r[1] or r[0][:12]} for r in db.execute('SELECT public_key,name FROM repeaters ORDER BY name COLLATE NOCASE') if re.fullmatch('[0-9a-fA-F]{64}',r[0] or '')]
    except (sqlite3.Error,OSError):
        return []


def select(key):
    if key and key not in {r['public_key'] for r in known_repeaters()}:
        raise ValueError('Select a repeater from Known repeaters.')
    with closing(connect()) as db, db:
        row=db.execute('SELECT * FROM selection WHERE id=1').fetchone()
        if row and row['public_key']==key:
            return
        db.execute('INSERT OR REPLACE INTO selection VALUES(1,?,?)',(key,time.time()))


def track(key, enabled=True):
    if key not in {r['public_key'] for r in known_repeaters()}:
        raise ValueError('Select a known repeater.')
    if type(enabled) is not bool:
        raise ValueError('Collection enabled must be true or false.')
    with closing(connect()) as db, db:
        legacy = db.execute('SELECT since FROM selection WHERE public_key=?', (key,)).fetchone()
        since = legacy['since'] if legacy else time.time()
        db.execute('''INSERT INTO subscriptions(public_key,since,enabled) VALUES (?,?,?)
            ON CONFLICT(public_key) DO UPDATE SET enabled=excluded.enabled''', (key,since,int(enabled)))


def collection_targets(db):
    targets = {row['public_key']: dict(row) for row in db.execute('SELECT public_key,since,enabled FROM subscriptions')}
    legacy = db.execute('SELECT public_key,since FROM selection WHERE id=1').fetchone()
    if legacy and legacy['public_key'] and legacy['public_key'] not in targets:
        targets[legacy['public_key']] = dict(legacy, enabled=1)
    return [row for row in targets.values() if row['enabled']]


def store_batch(db, batch, repeaters):
    # Serialize subscription reads and inserts with removal, so queued packets
    # cannot recreate observations after deletion.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    for selection in collection_targets(db):
        for at, packet in batch:
            if at < selection['since']:
                continue
            values = attribute(packet, selection['public_key'], repeaters)
            if values:
                db.execute('''INSERT INTO observations(target,at,digest,kind,scoped,ambiguous,first_hop,middle_hop,last_hop,route,previous,following)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (selection['public_key'], at, *values))


def normalize(rx):
    # Direct paths are not a forwarding history. Trace paths have special encoding.
    try:
        route_type, kind = int(rx['route_type']), int(rx['payload_type'])
        if route_type not in (0,1) or kind==9 or not 0<=kind<=15:
            return None
        count,size=int(rx['path_len']),int(rx['path_hash_size'])
        raw=rx['path']
        if not isinstance(raw,(str,bytes,bytearray)): return None
        raw=bytes.fromhex(raw) if isinstance(raw,str) else bytes(raw)
        if size not in (1,2,3) or not 0<=count<=63 or len(raw)!=count*size or len(raw)>64:
            return None
        payload=rx.get('pkt_payload')
        digest=None
        if isinstance(payload,(bytes,bytearray)) and 0<len(payload)<=1024:
            digest=hashlib.sha256(bytes([kind])+bytes(payload)).hexdigest()
        rssi = rx.get('rssi', rx.get('last_rssi'))
        snr = rx.get('snr', rx.get('last_snr'))
        return {'path':[raw[i:i+size].hex() for i in range(0,len(raw),size)],
                'hash_size':size,'kind':kind,'scoped':int(route_type==0),'digest':digest,
                'rssi':float(rssi) if type(rssi) in (int,float) and -300<rssi<50 else None,
                'snr':float(snr) if type(snr) in (int,float) and -100<snr<100 else None}
    except (KeyError,TypeError,ValueError,OverflowError):
        return None


def attribute(packet, target, repeaters):
    indices=[i for i,prefix in enumerate(packet['path']) if target.startswith(prefix)]
    if not indices:
        return None
    keys={r['public_key']:r['name'] for r in repeaters}
    keys.setdefault(target,target[:12])
    def resolve(prefix):
        matches=[key for key in keys if key.startswith(prefix)]
        return {'key':matches[0] if len(matches)==1 else prefix,
                'name':keys[matches[0]] if len(matches)==1 else prefix,
                'status':'matched' if len(matches)==1 else 'ambiguous' if matches else 'unknown'}
    route=[resolve(prefix) for prefix in packet['path']]
    ambiguous=any(route[i]['status']!='matched' for i in indices)
    previous=[route[i-1] for i in indices if i>0]
    following=[route[i+1] for i in indices if i+1<len(route)]
    return (packet['digest'],packet['kind'],packet['scoped'],int(ambiguous),
            int(0 in indices),int(any(0<i<len(route)-1 for i in indices)),int(len(route)-1 in indices),
            json.dumps(route),json.dumps(previous),json.dumps(following))


class Collector:
    def __init__(self):
        self.queue=queue.Queue(maxsize=2048)
        self.stop=threading.Event()
        self.thread=None
        self.dropped=0
        self.error=''

    def start(self):
        initialize()
        self.stop.clear()
        self.thread=threading.Thread(target=self.run,name='passive-repeater-statistics',daemon=True)
        self.thread.start()

    def submit(self,rx):
        if not self.thread or not self.thread.is_alive():
            return
        packet=normalize(rx)
        if packet is not None:
            try:
                self.queue.put_nowait((time.time(),packet))
            except queue.Full:
                self.dropped+=1

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)

    def run(self):
        repeaters=[]; refresh=0; prune=0; persisted_drops=0; heartbeat=0
        from meshcorestation.storage import optimizer_store
        optimizer_store.initialize()
        while not self.stop.is_set() or not self.queue.empty():
            # Batch writes once per second; idle health updates only every five seconds.
            self.stop.wait(1)
            batch=[]
            while len(batch)<256:
                try: batch.append(self.queue.get_nowait())
                except queue.Empty: break
            try:
                now=time.time()
                if not batch and now-heartbeat<5:
                    continue
                if now-refresh>=10:
                    repeaters=known_repeaters(); refresh=now
                limits=optimizer_store.config()
                # Budget covers this detailed-statistics SQLite file and its WAL.
                # When the safety threshold is reached, stop inserting rather than
                # risk filling the Pi SD card. Old records are still pruned.
                used=sum(os.path.getsize(p) for p in (str(STATS_PATH),str(STATS_PATH)+'-wal')
                         if os.path.exists(p))
                free=shutil.disk_usage(STATS_PATH.parent).free
                logical_used=used
                if used>=limits['budget_mb']*1048576:
                    # SQLite can reuse freed pages without shrinking the physical file.
                    # Let collection resume after time-based cleanup has freed enough.
                    with closing(connect()) as check:
                        freed=check.execute('PRAGMA freelist_count').fetchone()[0]
                        page_size=check.execute('PRAGMA page_size').fetchone()[0]
                    logical_used=max(0,used-freed*page_size)
                writable=(logical_used < limits['budget_mb']*1048576 and
                          free > limits['reserve_mb']*1048576)
                with closing(connect()) as db, db:
                    if not writable:
                        self.dropped+=len(batch)
                        self.error='Passive collection paused: storage budget or free-space reserve reached.'
                    else:
                        for at,packet in batch:
                            db.execute("""INSERT INTO network_observations
                              (at,kind,scoped,path_len,hash_size,route,digest,rssi,snr)
                              VALUES(?,?,?,?,?,?,?,?,?)""",
                              (at,packet['kind'],packet['scoped'],len(packet['path']),
                               packet['hash_size'],'|'.join(packet['path']),
                               packet['digest'],packet['rssi'],packet['snr']))
                            day=int(at//86400)
                            db.execute("""INSERT INTO network_daily VALUES(?,?,?,1)
                                ON CONFLICT(day,kind,scoped) DO UPDATE SET copies=copies+1""",
                                (day,packet['kind'],packet['scoped']))
                    if writable:
                        # Preserve 3.0.5 subscriptions: attribute each packet to
                        # every enabled managed repeater, not one global selection.
                        # The same transaction serializes with repeater removal.
                        store_batch(db, batch, repeaters)
                    if now-prune>=60:
                        cutoff=now-limits['retention_days']*86400
                        db.execute('DELETE FROM observations WHERE at<?',(cutoff,))
                        db.execute('DELETE FROM network_observations WHERE at<?',(cutoff,))
                        db.execute('DELETE FROM network_daily WHERE day<?',
                                   (int((now-limits['summary_days']*86400)//86400),))
                        # If data is still over budget, discard oldest chunks.
                        if logical_used>=limits['budget_mb']*1048576 or free<=limits['reserve_mb']*1048576:
                            db.execute('DELETE FROM network_observations WHERE id IN (SELECT id FROM network_observations ORDER BY at LIMIT 10000)')
                            db.execute('DELETE FROM observations WHERE id IN (SELECT id FROM observations ORDER BY at LIMIT 10000)')
                            db.execute('UPDATE health SET trimmed_at=? WHERE id=1',(now,))
                        prune=now
                        optimizer_store.cleanup(now)
                    drops=self.dropped
                    db.execute("UPDATE health SET heartbeat=?,dropped=dropped+?,error='' WHERE id=1",(now,drops-persisted_drops))
                persisted_drops=drops
                heartbeat=now
                if writable:
                    self.error=''
            except Exception as exc:
                self.dropped+=len(batch)
                self.error=str(exc)
                logging.warning('Passive statistics collector: %s',exc)
                # Keep bot processing independent of statistics storage errors.
                if self.stop.wait(1): break


collector=Collector()


def snapshot(days, public_key=None):
    if days not in (1,7,30): raise ValueError('Choose 24 hours, 7 days or 30 days.')
    if public_key is not None and public_key not in {r['public_key'] for r in known_repeaters()}:
        raise ValueError('Select a known repeater.')
    now=time.time(); cutoff=now-days*86400
    step=3600 if days==1 else 86400
    # Aggregate in SQLite instead of loading months of observations into Pi memory.
    with closing(connect()) as db:
        db.execute('BEGIN')
        selected=db.execute('SELECT * FROM selection WHERE id=1').fetchone()
        key=selected['public_key'] if selected else ''
        if public_key is not None and public_key != key:
            key=public_key
            first=db.execute('SELECT MIN(at) FROM observations WHERE target=?', (key,)).fetchone()[0]
            selected={'public_key':key,'since':first or now}
        subscription=db.execute('SELECT * FROM subscriptions WHERE public_key=?',(key,)).fetchone()
        collecting=any(row['public_key']==key for row in collection_targets(db))
        if subscription:
            selected={'public_key':key,'since':subscription['since']}
        params=(key,cutoff)
        where='target=? AND at>=? AND ambiguous=0'
        totals=db.execute('SELECT COUNT(*) AS copies, COUNT(digest) AS identified, COUNT(DISTINCT digest) AS unique_count, COALESCE(SUM(first_hop),0) AS first, COALESCE(SUM(middle_hop),0) AS middle, COALESCE(SUM(last_hop),0) AS final, COALESCE(SUM(scoped),0) AS scoped FROM observations WHERE '+where,params).fetchone()
        ambiguous=db.execute('SELECT COUNT(*) FROM observations WHERE target=? AND at>=? AND ambiguous=1',params).fetchone()[0]
        earliest=db.execute('SELECT MIN(at) FROM observations WHERE target=?',(key,)).fetchone()[0]
        health=dict(db.execute('SELECT * FROM health WHERE id=1').fetchone())
        buckets={row['bucket']:dict(row) for row in db.execute('SELECT CAST(at / ? AS INTEGER)*? AS bucket,COUNT(*) AS copies,COUNT(DISTINCT digest) AS unique_count FROM observations WHERE '+where+' GROUP BY bucket',(step,step,*params))}
        types={KINDS.get(row[0],f'Other ({row[0]})'):row[1] for row in db.execute('SELECT kind,COUNT(*) FROM observations WHERE '+where+' GROUP BY kind',params)}
        routes=[{'path':json.loads(row[0]),'count':row[1]} for row in db.execute('SELECT route,COUNT(*) AS n FROM observations WHERE '+where+' GROUP BY route ORDER BY n DESC LIMIT 20',params)]
        def neighbors(column):
            # Column is one of the two internal constants below, never user input.
            query="WITH grouped AS (SELECT "+column+" AS hops,COUNT(*) AS copies FROM observations WHERE "+where+" GROUP BY "+column+") SELECT json_extract(j.value,'$.key') AS key,json_extract(j.value,'$.name') AS name,json_extract(j.value,'$.status') AS status,SUM(grouped.copies) AS count FROM grouped,json_each(grouped.hops) AS j GROUP BY 1,2,3 ORDER BY count DESC LIMIT 30"
            return [dict(row) for row in db.execute(query,params)]
        previous,following=neighbors('previous'),neighbors('following')
        from meshcorestation.storage.repeater_usefulness import summarize
        usefulness=summarize(db,key,selected['since'] if selected else None,days,now,health,DB_PATH)
    unique=totals['unique_count']; repeats=totals['identified']-unique
    timeline=[]
    for at in range(int(cutoff//step)*step,int(now//step)*step+1,step):
        bucket=buckets.get(at,{})
        timeline.append({'at':at,'copies':bucket.get('copies',0),'unique':bucket.get('unique_count',0)})
    from meshcorestation.bridge import bridge
    return {'collection_enabled': collecting, 'selection':dict(selected) if selected else None,'repeaters':known_repeaters(),'days':days,
            'copies':totals['copies'],'unique':unique,'repeated':repeats,'ratio':repeats/totals['identified'] if totals['identified'] else None,
            'unidentified':totals['copies']-totals['identified'],'ambiguous':ambiguous,'earliest':earliest,
            'health':{**health,'running':bool(collector.thread and collector.thread.is_alive()),'error':collector.error,'radio':bridge.status[0]},
            'timeline':timeline,'types':types,'roles':{'First':totals['first'],'Middle':totals['middle'],'Final':totals['final']},
            'usefulness':usefulness,'scoped':totals['scoped'],'routes':routes,'previous':previous,'following':following}


def network_snapshot(key, days=7):
    """SQL-filtered radio observations; all repeaters are collected independently.

    Matches a repeater against path prefixes with collision-aware confidence.
    Packet lengths are observed route lengths, not required destination hops.
    """
    if days not in (1,7,14,30,60):
        raise ValueError('Choose 1, 7, 14, 30 or 60 days.')
    if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('Invalid repeater public key.')
    now=time.time(); cutoff=now-days*86400
    from meshcorestation.storage import optimizer_store
    excluded=optimizer_store.offline_intervals(key,cutoff,now)
    exclude_sql,exclude_args=optimizer_store.exclusion_sql(excluded)
    offline_seconds=sum(b-a for a,b in excluded)
    with closing(connect()) as db:
        db.execute('BEGIN')
        from meshcorestation.storage import optimizer_store
        other_keys={r['public_key'] for r in known_repeaters()}
        other_keys.add(key)
        prefixes=[key[:n] for n in (2,4,6)]
        # Use a complete route segment match, not a substring of another hash.
        predicates=' OR '.join("('|' || route || '|') LIKE ?" for _ in prefixes)
        parameters=['%|'+p+'|%' for p in prefixes]
        query=f"""SELECT at,kind,scoped,path_len,hash_size,route,digest,rssi,snr
                    FROM network_observations WHERE at>=? AND at<=? AND ({predicates}){exclude_sql}"""
        selected=db.execute(query,(cutoff,now,*parameters,*exclude_args))
        scope={label:{'count':0,'target':0,'hist':{}} for label in ('scoped','unscoped')}
        matches=0;ambiguous=0;active=set()
        for item in selected:
            size=item['hash_size'];prefix=key[:size*2]
            route=item['route'].split('|') if item['route'] else []
            if prefix not in route:
                continue
            label='scoped' if item['scoped'] else 'unscoped'
            scope[label]['count']+=1
            # Known hash collision is a hard ambiguity; unknown contacts remain
            # an uncertainty that prevents claiming complete mesh visibility.
            collision=sum(other.startswith(prefix) for other in other_keys)>1
            if collision:
                ambiguous+=1
            else:
                matches+=1;scope[label]['target']+=1
                hops=item['path_len']
                hist=scope[label]['hist']
                hist[hops]=hist.get(hops,0)+1
            active.add(int(item['at']//86400))
        totals=db.execute(f"""SELECT COUNT(*) copies,COUNT(DISTINCT digest) unique_digests,
                          COALESCE(SUM(scoped=0),0) unscoped
                          FROM network_observations WHERE at>=? AND at<=? {exclude_sql}""",(cutoff,now,*exclude_args)).fetchone()
        health=db.execute('SELECT * FROM health WHERE id=1').fetchone()
        first=db.execute('SELECT MIN(at) FROM network_observations').fetchone()[0]
        days_daily=[dict(r) for r in db.execute('SELECT day,kind,scoped,copies FROM network_daily WHERE day>=? ORDER BY day',(int(cutoff//86400),))]
        if excluded:
            days_daily=[dict(r) for r in db.execute(f'SELECT CAST(at/86400 AS INTEGER) day,kind,scoped,COUNT(*) copies FROM network_observations WHERE at>=? AND at<=? {exclude_sql} GROUP BY day,kind,scoped ORDER BY day',(cutoff,now,*exclude_args))]
    used=sum(os.path.getsize(p) for p in (str(STATS_PATH),str(STATS_PATH)+'-wal') if os.path.exists(p))
    free=shutil.disk_usage(STATS_PATH.parent).free
    return {'last_downtime_end':excluded[-1][1] if excluded else None,'excluded_downtime_seconds':offline_seconds,'usable_hours':(now-cutoff-offline_seconds)/3600,
            'now':now,'days':days,'copies':totals['copies'],
            'unique_digests':totals['unique_digests'],'unscoped':totals['unscoped'],
            'matching_copies':matches,'ambiguous':ambiguous,'active_days':len(active),
            'scope':scope,'daily':days_daily,'first_at':first,
            'partial':first is None or first>cutoff or bool(health['trimmed_at'] and health['trimmed_at']>=cutoff),
            'collector_error':collector.error or health['error'],
            'storage':{'bytes':used,'free_bytes':free}}
