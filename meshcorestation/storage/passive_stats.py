"""Passive, selected-repeater observations. No radio commands or payload storage."""
from contextlib import closing
import hashlib
import json
import logging
import queue
import re
import sqlite3
import threading
import time
from meshcorestation.config import DATA_DIR, DB_PATH

STATS_PATH = DATA_DIR / 'repeater-statistics.db'
RETENTION = 30 * 86400
MAX_ROWS = 200000
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
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY, target TEXT NOT NULL, at REAL NOT NULL, digest TEXT,
                kind INTEGER NOT NULL, scoped INTEGER NOT NULL, ambiguous INTEGER NOT NULL,
                first_hop INTEGER NOT NULL, middle_hop INTEGER NOT NULL, last_hop INTEGER NOT NULL,
                route TEXT NOT NULL, previous TEXT NOT NULL, following TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS observations_target_at ON observations(target, at);
            CREATE INDEX IF NOT EXISTS observations_at ON observations(at);
            CREATE TABLE IF NOT EXISTS health (id INTEGER PRIMARY KEY CHECK(id=1), heartbeat REAL, dropped INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', trimmed_at REAL);
            INSERT OR IGNORE INTO health(id) VALUES(1);
        ''')


def known_repeaters():
    with closing(sqlite3.connect(DB_PATH.as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
        return [{'public_key':r[0].lower(),'name':r[1] or r[0][:12]} for r in db.execute('SELECT public_key,name FROM repeaters ORDER BY name COLLATE NOCASE') if re.fullmatch('[0-9a-fA-F]{64}',r[0] or '')]


def select(key):
    if key and key not in {r['public_key'] for r in known_repeaters()}:
        raise ValueError('Select a repeater from Known repeaters.')
    with closing(connect()) as db, db:
        row=db.execute('SELECT * FROM selection WHERE id=1').fetchone()
        if row and row['public_key']==key:
            return
        db.execute('INSERT OR REPLACE INTO selection VALUES(1,?,?)',(key,time.time()))


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
        if size not in (1,2,3) or not 1<=count<=63 or len(raw)!=count*size or len(raw)>64:
            return None
        payload=rx.get('pkt_payload')
        digest=None
        if isinstance(payload,(bytes,bytearray)) and 0<len(payload)<=1024:
            digest=hashlib.sha256(bytes([kind])+bytes(payload)).hexdigest()
        return {'path':[raw[i:i+size].hex() for i in range(0,len(raw),size)],'kind':kind,'scoped':int(route_type==0),'digest':digest}
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
                with closing(connect()) as db, db:
                    selection=db.execute('SELECT * FROM selection WHERE id=1').fetchone()
                    if selection and selection['public_key']:
                        for at,packet in batch:
                            if at<selection['since']: continue
                            values=attribute(packet,selection['public_key'],repeaters)
                            if values:
                                db.execute('INSERT INTO observations(target,at,digest,kind,scoped,ambiguous,first_hop,middle_hop,last_hop,route,previous,following) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(selection['public_key'],at,*values))
                    if now-prune>=60:
                        db.execute('DELETE FROM observations WHERE at<?',(now-RETENTION,))
                        boundary=db.execute('SELECT id,at FROM observations ORDER BY id DESC LIMIT 1 OFFSET ?',(MAX_ROWS,)).fetchone()
                        if boundary:
                            db.execute('DELETE FROM observations WHERE id<=?',(boundary['id'],))
                            db.execute('UPDATE health SET trimmed_at=? WHERE id=1',(now,))
                        prune=now
                    drops=self.dropped
                    db.execute("UPDATE health SET heartbeat=?,dropped=dropped+?,error='' WHERE id=1",(now,drops-persisted_drops))
                persisted_drops=drops
                heartbeat=now
                self.error=''
            except Exception as exc:
                self.dropped+=len(batch)
                self.error=str(exc)
                logging.warning('Passive statistics collector: %s',exc)
                # Keep bot processing independent of statistics storage errors.
                if self.stop.wait(1): break


collector=Collector()


def snapshot(days):
    if days not in (1,7,30): raise ValueError('Choose 24 hours, 7 days or 30 days.')
    now=time.time(); cutoff=now-days*86400
    step=3600 if days==1 else 86400
    # Aggregate in SQLite instead of loading months of observations into Pi memory.
    with closing(connect()) as db:
        db.execute('BEGIN')
        selected=db.execute('SELECT * FROM selection WHERE id=1').fetchone()
        key=selected['public_key'] if selected else ''
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
            query="SELECT json_extract(j.value,'$.key') AS key,json_extract(j.value,'$.name') AS name,json_extract(j.value,'$.status') AS status,COUNT(*) AS count FROM observations,json_each(observations."+column+") AS j WHERE "+where+" GROUP BY 1,2,3 ORDER BY count DESC LIMIT 30"
            return [dict(row) for row in db.execute(query,params)]
        previous,following=neighbors('previous'),neighbors('following')
    unique=totals['unique_count']; repeats=totals['identified']-unique
    timeline=[]
    for at in range(int(cutoff//step)*step,int(now//step)*step+1,step):
        bucket=buckets.get(at,{})
        timeline.append({'at':at,'copies':bucket.get('copies',0),'unique':bucket.get('unique_count',0)})
    from meshcorestation.bridge import bridge
    return {'selection':dict(selected) if selected else None,'repeaters':known_repeaters(),'days':days,
            'copies':totals['copies'],'unique':unique,'repeated':repeats,'ratio':repeats/totals['identified'] if totals['identified'] else None,
            'unidentified':totals['copies']-totals['identified'],'ambiguous':ambiguous,'earliest':earliest,
            'health':{**health,'running':bool(collector.thread and collector.thread.is_alive()),'error':collector.error,'radio':bridge.status[0]},
            'timeline':timeline,'types':types,'roles':{'First':totals['first'],'Middle':totals['middle'],'Final':totals['final']},
            'scoped':totals['scoped'],'routes':routes,'previous':previous,'following':following}
