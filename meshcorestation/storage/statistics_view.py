"""SQLite aggregates of saved passive evidence; no radio/network calls."""
from contextlib import closing, contextmanager
from functools import lru_cache
import hashlib
import hmac
import json
import logging
import os
import shutil
import tempfile
from bisect import bisect_right
from datetime import datetime, timedelta
from collections import OrderedDict
from pathlib import Path
import re
import sqlite3
import time

from meshcorestation.storage.connection import connect as open_database
from meshcorestation.storage import passive_stats

REGIONS_SCHEMA = '''CREATE TABLE IF NOT EXISTS statistics_regions(
 name TEXT PRIMARY KEY,scope_key TEXT NOT NULL)'''
COUNTS = '''COUNT(*) AS receptions,COUNT(DISTINCT packet_digest) AS unique_packets,
 COUNT(packet_digest)-COUNT(DISTINCT packet_digest) AS repeated,
 COUNT(*)-COUNT(packet_digest) AS unidentified'''


def region_config(main_path):
    with closing(open_database(Path(main_path).as_uri()+'?mode=ro',timeout=2)) as db:
        return [dict(r) for r in db.execute('SELECT name,scope_key FROM statistics_regions ORDER BY name')]


def save_regions(main_path, rows):
    if not isinstance(rows,list) or len(rows)>64: raise ValueError('Configure up to 64 region names.')
    values=[];names=set()
    for row in rows:
        if not isinstance(row,dict): raise ValueError('Invalid region configuration.')
        name=row.get('name','').strip().removeprefix('#') if isinstance(row.get('name'),str) else ''
        if not re.fullmatch('[A-Za-z0-9_-]{1,30}',name) or name.lower() in {'unknown','unscoped'} or name.lower() in names:
            raise ValueError('Use distinct region names, 1–30 letters, digits, hyphens or underscores. Unknown and Unscoped are reserved.')
        key=row.get('scope_key') or hashlib.sha256(('#'+name).encode()).digest()[:16].hex()
        if not isinstance(key,str) or not re.fullmatch('[0-9a-fA-F]{32}',key):raise ValueError('A custom region key must contain 32 hexadecimal characters.')
        names.add(name.lower());values.append((name,key.lower()))
    with closing(open_database(Path(main_path).as_uri()+'?mode=rw',timeout=2)) as db,db:
        db.execute('DELETE FROM statistics_regions')
        db.executemany('INSERT INTO statistics_regions VALUES(?,?)',values)


def scope_resolver(regions):
    keys={}
    for row in regions:
        try:
            key=bytes.fromhex(row['scope_key'])
            name=row['name'].removeprefix('#')
            if len(key)==16 and name.lower() not in {'unknown','unscoped'}:keys.setdefault(key,set()).add(name)
        except (ValueError,TypeError,KeyError):continue
    @lru_cache(maxsize=4096)
    def resolve(kind,payload,transport,route_type):
        if route_type==1:return 'Unscoped'
        if route_type!=0:return 'Unknown'
        try:
            code=bytes.fromhex(transport)
            if len(code)!=4:return 'Unknown'
            received=int.from_bytes(code[:2],'little')
            if received==0:return 'Unscoped'  # MeshCore wildcard transport scope.
            if not isinstance(payload,bytes):return 'Unknown'
            matches=set()
            for key,names in keys.items():
                value=int.from_bytes(hmac.new(key,bytes([kind])+payload,hashlib.sha256).digest()[:2],'little')
                value=1 if value==0 else 65534 if value==65535 else value
                if received==value:matches.update(names)
            return next(iter(matches)) if len(matches)==1 else 'Unknown'
        except (TypeError,ValueError,OverflowError):return 'Unknown'
    return resolve


QUERY_BUDGET_SECONDS = 8.0
LOGGER = logging.getLogger('meshcorestation.statistics')


class QueryTimeout(RuntimeError):
    def __init__(self,stage,diagnostics=None):
        self.stage=stage
        self.diagnostics=diagnostics or {}
        super().__init__('Saved statistics exceeded the query budget during '+stage+'.')


class Diagnostics:
    def __init__(self,budget):
        self.started=time.monotonic();self.cpu_started=time.process_time();self.deadline=self.started+budget
        self.current='setup';self.times={};self.rows=0

    def report(self):
        return dict(source_rows=self.rows,elapsed_ms=round((time.monotonic()-self.started)*1000,3),cpu_ms=round((time.process_time()-self.cpu_started)*1000,3),stages_ms=self.times)

    def check(self):
        if time.monotonic()>=self.deadline:raise QueryTimeout(self.current,self.report())

    @contextmanager
    def stage(self,name):
        self.current=name;start=time.monotonic()
        try:
            self.check();yield;self.check()
        except sqlite3.OperationalError as exc:
            if getattr(exc,'sqlite_errorcode',None)==sqlite3.SQLITE_INTERRUPT or time.monotonic()>=self.deadline:
                raise QueryTimeout(name,self.report()) from None
            raise
        finally:
            elapsed=round((time.monotonic()-start)*1000,3);self.times[name]=elapsed
            LOGGER.debug('Statistics stage=%s elapsed_ms=%.3f rows=%d',name,elapsed,self.rows)


class RouteCache:
    """Parse each reused route once, bounded by entries and estimated heap bytes."""
    def __init__(self,key,resolve_hash):
        self.key,self.resolve_hash=key,resolve_hash
        self.cache=OrderedDict();self.used=0;self.parsed=0

    def get(self,route):
        saved=self.cache.get(route)
        if saved is not None:
            self.cache.move_to_end(route);return saved[0]
        self.parsed+=1
        try:
            hops=json.loads(route)
            if not isinstance(hops,list) or any(not isinstance(h,dict) or not isinstance(h.get('hash'),str) for h in hops):raise ValueError()
        except (ValueError,TypeError):raise sqlite3.DatabaseError('Saved route evidence is malformed.') from None
        confirmed=any(h.get('status')=='matched' and self.resolve_hash(h['hash'])==self.key for h in hops)
        edges=set()
        for i,target in enumerate(hops):
            prefix=target['hash']
            if not prefix or not self.key.startswith(prefix):continue
            for offset,direction in ((-1,'incoming'),(1,'outgoing')):
                if not 0<=i+offset<len(hops):continue
                neighbor=hops[i+offset];other=neighbor['hash']
                neighbor_key=self.resolve_hash(other)
                verified=(target.get('status')=='matched' and neighbor.get('status')=='matched'
                          and self.resolve_hash(prefix)==self.key and neighbor_key is not None)
                edges.add((prefix,other,neighbor_key,direction,bool(verified)))
        value=(confirmed,tuple(edges));weight=len(route)*4+len(edges)*256+256
        if weight<=8*1024*1024:
            while self.cache and (self.used+weight>8*1024*1024 or len(self.cache)>=1024):
                _,(_,old_weight)=self.cache.popitem(last=False);self.used-=old_weight
            self.cache[route]=(value,weight);self.used+=weight
        return value


def _space_guard(main_path,extra=0):
    # SQLite scratch work must not consume the passive collector's free-space
    # reserve. Check SQLite's configured temp volume and the source-data volume.
    directories={Path(main_path).parent,Path(os.environ.get('SQLITE_TMPDIR') or tempfile.gettempdir())}
    for directory in directories:
        if shutil.disk_usage(directory).free<passive_stats.MIN_FREE_BYTES+8*1024*1024+extra:
            raise OSError('Insufficient statistics scratch space; collection reserve is protected.')


def _spool(source,work,key,resolve_hash,regions,start,end,diagnostics,main_path):
    """One indexed source scan. Only compact, disposable facts enter the spool.

    No source-schema writes or membership lock. The anonymous SQLite file is
    deleted on close and has a 2 MiB page cache; raw payload/history never enters
    the browser or a Python list of the complete observation history.
    """
    work.executescript('''PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        PRAGMA temp_store=FILE; PRAGMA cache_size=-2048;
        CREATE TABLE facts(id INTEGER PRIMARY KEY,digest TEXT,at REAL,bucket INTEGER,
          kind INTEGER,hop INTEGER,confirmed INTEGER,region TEXT,origin INTEGER);
        CREATE TABLE edges(identity TEXT,direction TEXT,verified INTEGER,digest BLOB,at REAL);''')
    routes=RouteCache(key,resolve_hash);region_name=scope_resolver(regions)
    rows=source.execute('''SELECT id,received_at,packet_digest,packet_type,route_type,
        ambiguous,first_hop,middle_hop,last_hop,hop_count,route,payload,transport_code,evidence
        FROM observations WHERE received_at>=? AND received_at<?''',(start,end))
    while True:
        batch=rows.fetchmany(128)
        if not batch:break
        diagnostics.check();_space_guard(main_path);facts=[];edge_facts=[]
        for row in batch:
            oid,at,digest,kind,route_type,ambiguous,first,middle,last,hop,route,payload,transport,evidence=row
            observed=route_type in (0,1) and kind!=9
            matched,links=routes.get(route) if observed else (False,())
            confirmed=int(observed and not ambiguous and (first or middle or last) and matched)
            region=region_name(kind,payload,transport,route_type) if confirmed else None
            # SHA-256 identifiers remain exact; compact lowercase digests only
            # in this disposable spool (noncanonical stored strings stay strings).
            if isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest):digest=bytes.fromhex(digest)
            # Full advertised origin is independent of route-hash ambiguity.
            origin=int(kind==4 and evidence=='advertisement-origin' and isinstance(payload,bytes)
                       and len(payload)>=101 and payload[:32].hex()==key and payload[100]&15==2)
            facts.append((oid,digest,at,int(at//3600)*3600,kind,hop,confirmed,region,origin))
            # Deduplicate a direction within this reception, never across RX copies.
            edges={(neighbor_key if valid and not ambiguous else prefix+' → '+other,direction,int(valid and not ambiguous))
                   for prefix,other,neighbor_key,direction,valid in links}
            edge_facts.extend((identity,direction,valid,digest,at) for identity,direction,valid in edges)
        work.executemany('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?)',facts)
        work.executemany('INSERT INTO edges VALUES(?,?,?,?,?)',edge_facts)
        diagnostics.rows+=len(batch)
        # Yield the GIL to the radio loop/collector between bounded batches.
        time.sleep(0)
    return routes


def _calendar_boundaries(start,end,zone):
    """Real local-hour boundaries, including folds and excluding skipped hours."""
    day=datetime.fromtimestamp(start,zone).date()-timedelta(days=1)
    last=datetime.fromtimestamp(end,zone).date()+timedelta(days=1)
    points=set()
    while day<=last:
        for hour in range(24):
            for fold in (0,1):
                local=datetime(day.year,day.month,day.day,hour,tzinfo=zone,fold=fold)
                at=local.timestamp();back=datetime.fromtimestamp(at,zone)
                if back.date()==day and back.hour==hour and back.minute==0:points.add(at)
        day+=timedelta(days=1)
    return sorted(points)


def _coverage(source,start,end,diagnostics,local_bounds):
    buckets={};local_buckets={};known=bool(source.execute("SELECT 1 FROM sqlite_master WHERE name='collection_windows'").fetchone())
    if not known:return buckets,False,local_buckets
    pending=None
    def add(lo,hi):
        lo,hi=max(start,lo),min(end,hi)
        for bucket in range(int(lo//3600)*3600,int(hi//3600)*3600+1,3600):
            overlap=max(0,min(hi,bucket+3600)-max(lo,bucket))
            if overlap:buckets[bucket]=buckets.get(bucket,0)+overlap
        i=max(0,bisect_right(local_bounds,lo)-1)
        while i+1<len(local_bounds) and local_bounds[i]<hi:
            bucket,until=local_bounds[i:i+2]
            overlap=max(0,min(hi,until)-max(lo,bucket))
            if overlap:local_buckets[bucket]=local_buckets.get(bucket,0)+overlap
            i+=1
    for i,(lo,hi) in enumerate(source.execute('''SELECT started_at,ended_at FROM collection_windows
        WHERE ended_at>? AND started_at<? ORDER BY started_at''',(start,end))):
        if i%128==0:diagnostics.check()
        if pending and lo<=pending[1]:pending=(pending[0],max(pending[1],hi))
        else:
            if pending:add(*pending)
            pending=(lo,hi)
    if pending:add(*pending)
    return buckets,True,local_buckets


def aggregate(main_path,key,days=1,now=None):
    if days not in (1,7,30):raise ValueError('Choose 24 hours, 7 days or 30 days.')
    diagnostics=Diagnostics(QUERY_BUDGET_SECONDS)
    result=None;completed=False
    try:
        with diagnostics.stage('metadata'):
            status=passive_stats.snapshot(main_path,key)
            key=status['selected'];now=time.time() if now is None else now;start=now-days*86400
            with closing(open_database(Path(main_path).as_uri()+'?mode=ro',timeout=.25)) as main:
                registry={r['public_key']:dict(r) for r in main.execute('SELECT public_key,name,latitude,longitude FROM repeaters')}
                regions=[dict(r) for r in main.execute('SELECT name,scope_key FROM statistics_regions UNION SELECT name,scope_key FROM scopes')]
            prefixes={}
            for full in registry:
                for width in (2,4,6,8):prefixes.setdefault(full[:width],[]).append(full)
            def resolve_hash(prefix):
                matches=prefixes.get(prefix,[])
                return matches[0] if len(matches)==1 else None
            result=dict(ok=True,selected=key,days=days,start=start,end=now,generated_at=now,
                hourly=[],activity_hourly=[],packet_types=[],hops=[],regions=[],neighbors=[],ambiguous=[],totals={},excluded=0,
                coverage_seconds=0,coverage_expected=days*86400,coverage_known=False,
                selected_repeater=registry.get(key),notes=[])
            path=passive_stats.statistics_path(main_path,key) if key else None
            from meshcorestation.config import TIMEZONE
            local_bounds=_calendar_boundaries(start,now,TIMEZONE)
            result['activity_timezone']=TIMEZONE.key
            hourly={};activity={};coverage={};activity_coverage={}
        if path and path.exists():
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.25)) as source,closing(sqlite3.connect('')) as work:
                source.execute('PRAGMA query_only=ON');source.execute('BEGIN')
                source.set_progress_handler(lambda:int(time.monotonic()>=diagnostics.deadline),10000)
                work.set_progress_handler(lambda:int(time.monotonic()>=diagnostics.deadline),10000)
                with diagnostics.stage('classify'):
                    routes=_spool(source,work,key,resolve_hash,regions,start,now,diagnostics,main_path)
                work.row_factory=sqlite3.Row
                # Compact covering indexes, built only in this disposable spool.
                with diagnostics.stage('indexes'):
                    size=work.execute('PRAGMA page_count').fetchone()[0]*work.execute('PRAGMA page_size').fetchone()[0]
                    _space_guard(main_path,size*2)
                    work.executescript('''CREATE INDEX facts_confirmed_digest ON facts(confirmed,digest);
                      CREATE INDEX edges_group ON edges(verified,identity,direction,digest,at);''')
                with diagnostics.stage('totals'):
                    result['totals']=dict(work.execute('SELECT '+COUNTS.replace('packet_digest','digest')+' FROM facts WHERE confirmed=1').fetchone())
                    result['excluded']=diagnostics.rows-result['totals']['receptions']
                count_sql=COUNTS.replace('packet_digest','digest')
                with diagnostics.stage('hourly'):
                    hourly={r['bucket']:dict(r) for r in work.execute('SELECT bucket,'+count_sql+' FROM facts WHERE confirmed=1 AND kind IN (2,5) GROUP BY bucket')}
                with diagnostics.stage('activity'):
                    # Reuse compact facts; never parse routes or read source payloads again.
                    work.create_function('calendar_bucket',1,lambda at:local_bounds[bisect_right(local_bounds,at)-1],deterministic=True)
                    activity={r['bucket']:dict(r) for r in work.execute('SELECT calendar_bucket(at) AS bucket,'+count_sql+' FROM facts WHERE confirmed=1 AND origin=0 GROUP BY calendar_bucket(at)')}
                with diagnostics.stage('packet_types'):
                    result['packet_types']=[dict(r) for r in work.execute('''SELECT
                      CASE kind WHEN 5 THEN 'Group messages' WHEN 2 THEN 'Direct text messages'
                      WHEN 4 THEN 'Advertisements' ELSE 'Other MeshCore packet types' END AS category,
                      CASE WHEN origin=1 THEN 'advertisement-origin' ELSE 'observed-flood-route' END AS evidence,
                      '''+count_sql+''' FROM facts WHERE confirmed=1 OR origin=1
                      GROUP BY category,evidence ORDER BY category,evidence''')]
                    total=sum(r['receptions'] for r in result['packet_types'])
                    for row in result['packet_types']:row['percentage']=100*row['receptions']/total if total else 0
                with diagnostics.stage('hops'):
                    result['hops']=[dict(r) for r in work.execute('SELECT hop AS hop_count,'+count_sql+' FROM facts WHERE confirmed=1 GROUP BY hop ORDER BY receptions DESC,hop')]
                with diagnostics.stage('regions'):
                    result['regions']=[dict(r) for r in work.execute('SELECT region AS name,'+count_sql+' FROM facts WHERE confirmed=1 GROUP BY region ORDER BY receptions DESC,region')]
                    for row in result['regions']:row['percentage']=100*row['receptions']/result['totals']['receptions'] if result['totals']['receptions'] else 0
                with diagnostics.stage('neighbors'):
                    edge_rows=list(work.execute('''SELECT verified,identity,direction,COUNT(*) AS receptions,
                      COUNT(DISTINCT digest) AS unique_packets,MAX(at) AS last_observed
                      FROM edges GROUP BY verified,identity,direction
                      ORDER BY receptions DESC,verified,identity,direction LIMIT 1000'''))
                    grouped={}
                    for r in edge_rows:
                        r=dict(r)
                        if not r['verified']:
                            candidates=prefixes.get(r['identity'].split(' → ')[-1],[])
                            r.update(candidates=candidates[:64],candidate_count=len(candidates));result['ambiguous'].append(r);continue
                        if r['identity']==key:continue
                        item=grouped.setdefault(r['identity'],dict(registry[r['identity']],incoming=0,outgoing=0,last_observed=0))
                        item[r['direction']]=r['receptions'];item[r['direction']+'_unique']=r['unique_packets']
                        item['last_observed']=max(item['last_observed'],r['last_observed'])
                    result['neighbors']=list(grouped.values())
                    if len(edge_rows)>=1000:result['notes'].append('Neighbor output is limited to 1,000 grouped direction entries.')
                with diagnostics.stage('coverage'):
                    coverage,result['coverage_known'],activity_coverage=_coverage(source,start,now,diagnostics,local_bounds)
                result['diagnostics']=dict(source_rows=diagnostics.rows,parsed_routes=routes.parsed,route_cache_bytes=routes.used)
        with diagnostics.stage('render_series'):
            for bucket in range(int(start//3600)*3600,int(now//3600)*3600+1,3600):
                lo,hi=max(start,bucket),min(now,bucket+3600)
                if hi<=lo:continue
                seconds=min(hi-lo,coverage.get(bucket,0));result['coverage_seconds']+=seconds
                complete=seconds>=hi-lo-1e-6
                values=hourly.get(bucket) or dict(receptions=0 if complete else None,unique_packets=0 if complete else None,repeated=0 if complete else None,unidentified=0 if complete else None)
                result['hourly'].append(dict(at=bucket,coverage_seconds=seconds,expected_seconds=hi-lo,complete=complete,**values))
            for bucket,until in zip(local_bounds,local_bounds[1:]):
                lo,hi=max(start,bucket),min(now,until)
                if hi<=lo:continue
                seconds=min(hi-lo,activity_coverage.get(bucket,0));complete=seconds>=hi-lo-1e-6
                values=activity.get(bucket) or dict(receptions=0 if complete else None,unique_packets=0 if complete else None,repeated=0 if complete else None,unidentified=0 if complete else None)
                result['activity_hourly'].append(dict(at=bucket,until=until,interval_seconds=until-bucket,coverage_seconds=seconds,expected_seconds=hi-lo,complete=complete,**values))
            result['notes'].append('Adjacent flood-path observations are inferred relationships, not verified direct RF links or delivery confirmation.')
            result['notes'].append('Unique packets are distinct payload digests within each hour or ranking category; repeated receptions are additional copies in that group.')
        result.setdefault('diagnostics',{})['stages_ms']=diagnostics.times
        completed=True
        return result
    finally:
        (LOGGER.info if completed else LOGGER.warning)('Statistics aggregation outcome=%s rows=%d total_ms=%.3f stages_ms=%s','complete' if completed else 'failed',diagnostics.rows,(time.monotonic()-diagnostics.started)*1000,diagnostics.times)
