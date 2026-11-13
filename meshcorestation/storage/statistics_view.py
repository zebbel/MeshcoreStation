"""SQLite aggregates of saved passive evidence; no radio/network calls."""
from contextlib import closing, contextmanager, nullcontext
from functools import lru_cache
import hashlib
import hmac
import json
import logging
import math
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
from meshcorestation.storage.statistics_classification import (
    CACHE_BYTES, ClassificationCache, EDGE_COLUMNS, FACT_COLUMNS, source_anchor, source_marker,
)

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
    @lru_cache(maxsize=16)
    def keyed_prefixes(kind):
        prefix = bytes([kind])
        return [(hmac.new(key, prefix, 'sha256'), names) for key, names in keys.items()]

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
            for prefix,names in keyed_prefixes(kind):
                digest = prefix.copy()
                digest.update(payload)
                value = int.from_bytes(digest.digest()[:2], 'little')
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
        self.current='setup';self.times={};self.rows=0;self.classified=0

    def report(self):
        return dict(source_rows=self.rows,classified_rows=self.classified,elapsed_ms=round((time.monotonic()-self.started)*1000,3),cpu_ms=round((time.process_time()-self.cpu_started)*1000,3),stages_ms=self.times)

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
            elapsed=round((time.monotonic()-start)*1000,3);self.times[name]=round(self.times.get(name,0)+elapsed,3)
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
            hops = json.loads(route)
            if not isinstance(hops, list):
                raise ValueError()
            targets = []
            for i, hop in enumerate(hops):
                prefix = hop['hash']
                if not isinstance(prefix, str):
                    raise ValueError()
                if prefix and self.key.startswith(prefix):
                    targets.append((i, prefix))
        except (ValueError, TypeError, KeyError):
            raise sqlite3.DatabaseError('Saved route evidence is malformed.') from None
        confirmed = False
        edges = set()
        for i, prefix in targets:
            target_matches = hops[i].get('status') == 'matched' and self.resolve_hash(prefix) == self.key
            confirmed |= target_matches
            for offset, direction in ((-1, 'incoming'), (1, 'outgoing')):
                if not 0 <= i + offset < len(hops):
                    continue
                neighbor = hops[i + offset]
                other = neighbor['hash']
                neighbor_key = self.resolve_hash(other)
                verified = target_matches and neighbor.get('status') == 'matched' and neighbor_key is not None
                edges.add((prefix, other, neighbor_key, direction, verified))
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


HEX_DIGEST = re.compile('[0-9a-f]{64}')


def _source_rows(source, start, end, after_id=None):
    # Index range for sparse windows, sequential pages for dense history. The
    # latter avoids a table-page lookup in timestamp order for each reception.
    columns = """id,received_at,packet_digest,packet_type,route_type,ambiguous,
        first_hop,middle_hop,last_hop,hop_count,route,
        CASE WHEN route_type=0 OR (packet_type=4 AND evidence='advertisement-origin') THEN payload END,
        transport_code,evidence"""
    where = 'received_at>=? AND received_at<?'
    if after_id is not None:
        return source.execute(f'SELECT {columns} FROM observations NOT INDEXED WHERE id>? AND {where} ORDER BY id',
                              (after_id, start, end)), True
    count = source.execute(f'SELECT COUNT(*) FROM observations WHERE {where}', (start, end)).fetchone()[0]
    last_id = source.execute('SELECT MAX(id) FROM observations').fetchone()[0]
    dense = bool(last_id and count * 3 >= last_id)
    scan = ' NOT INDEXED' if dense else ''
    order = ' ORDER BY id' if dense else ''
    return source.execute(f'SELECT {columns} FROM observations{scan} WHERE {where}{order}', (start, end)), dense


def _spool(source,work,key,resolve_hash,regions,start,end,diagnostics,main_path,marker=None):
    """Build compact aggregate inputs, reusing valid overlap and reading only missing rows."""
    _space_guard(main_path)
    work.executescript(f"""PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        PRAGMA temp_store=FILE; PRAGMA cache_size=-2048;
        CREATE TABLE facts({FACT_COLUMNS});
        CREATE TABLE edges({EDGE_COLUMNS});""")
    routes = RouteCache(key, resolve_hash)
    region_name = scope_resolver(regions)
    if start >= end:
        return routes
    cache = ClassificationCache(work, main_path) if marker else None
    reused = None
    if cache:
        # Rollback must undo a partially loaded cache, so the work database
        # needs a journal when copying cached rows.
        work.execute('PRAGMA journal_mode=MEMORY')
        try:
            reused = cache.load(*marker, start, end, source)
        except (OSError, sqlite3.Error):
            diagnostics.check()
            cache = None
        work.execute('PRAGMA journal_mode=OFF')
    ranges = [(start, end, None)]
    if reused:
        lo, hi, last_id = reused
        ranges = [(start, lo, None), (hi, end, None)]
        if marker[1] > last_id:
            ranges.append((lo, hi, last_id))
    ranges = [(lo, hi, last_id) for lo, hi, last_id in ranges if lo < hi]
    checkpoint = None
    for index, (lo, hi, last_id) in enumerate(ranges):
        rows, ordered = _source_rows(source, lo, hi, last_id)
        last_processed = None
        while batch := rows.fetchmany(256):
            diagnostics.check()
            if (cache and ordered and (not reused or last_id is not None)
                    and index == len(ranges) - 1 and last_processed is not None
                    and diagnostics.deadline - time.monotonic() < .85):
                # Save only the completed ID prefix. The next request resumes
                # from it. Never aggregate or return a partially classified view.
                checkpoint = last_processed
                break
            if diagnostics.classified // 2048 != (diagnostics.classified + len(batch)) // 2048:
                _space_guard(main_path)
            facts, edge_facts = [], []
            for row in batch:
                oid,at,digest,kind,route_type,ambiguous,first,middle,last,hop,route,payload,transport,evidence=row
                observed=route_type in (0,1) and kind!=9
                matched,links=routes.get(route) if observed else (False,())
                confirmed=int(observed and not ambiguous and (first or middle or last) and matched)
                region = ('Unscoped' if route_type == 1 else region_name(kind,payload,transport,route_type)) if confirmed else None
                if isinstance(digest,str) and HEX_DIGEST.fullmatch(digest):digest=bytes.fromhex(digest)
                origin=int(kind==4 and evidence=='advertisement-origin' and isinstance(payload,bytes)
                           and len(payload)>=101 and payload[:32].hex()==key and payload[100]&15==2)
                facts.append((oid,digest,at,int(at//3600)*3600,kind,hop,confirmed,region,origin))
                edges={(neighbor_key if valid and not ambiguous else prefix+' → '+other,direction,int(valid and not ambiguous))
                       for prefix,other,neighbor_key,direction,valid in links}
                edge_facts.extend((identity,direction,valid,digest,at,oid) for identity,direction,valid in edges)
            work.executemany('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?)',facts)
            work.executemany('INSERT INTO edges VALUES(?,?,?,?,?,?)',edge_facts)
            diagnostics.classified += len(batch)
            last_processed = batch[-1][0]
    work.commit()
    diagnostics.rows = work.execute('SELECT COUNT(*) FROM facts').fetchone()[0]
    checkpoint_saved = False
    if cache and (not reused or diagnostics.classified or start < cache.previous[2] or end > cache.previous[3]):
        # Treat persistence as optional. Save only after the requested facts
        # are committed so a full/locked cache cannot discard the current view.
        try:
            _space_guard(main_path, CACHE_BYTES)
            highwater = marker[1] if checkpoint is None else checkpoint
            retain = checkpoint is None
            if retain and reused and highwater > reused[2]:
                # A new backdated row outside this view could make the old
                # coverage misleading. Current-time appends retain the overlap.
                retain = source.execute("""SELECT 1 FROM observations NOT INDEXED
                    WHERE id>? AND received_at>=? AND received_at<?
                    AND (received_at<? OR received_at>=?) LIMIT 1""",
                    (reused[2], *cache.previous[2:4], start, end)).fetchone() is None
            checkpoint_saved = cache.save(
                marker[0], highwater, start, end, reused, retain, source_anchor(source, highwater))
        except (OSError, sqlite3.Error):
            diagnostics.check()
    if checkpoint is not None:
        raise QueryTimeout(diagnostics.current, dict(diagnostics.report(), classification_progress_saved=checkpoint_saved))
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
    for lo,hi in _coverage_intervals(source,start,end,diagnostics):
        add(lo,hi)
    return buckets,True,local_buckets


def _coverage_intervals(source, start, end, diagnostics):
    if start >= end:
        return
    pending = None
    for i, (lo, hi) in enumerate(source.execute("""SELECT started_at,ended_at FROM collection_windows
        WHERE ended_at>? AND started_at<? ORDER BY started_at""", (start, end))):
        if i % 128 == 0:
            diagnostics.check()
        lo, hi = max(start, lo), min(end, hi)
        if pending and lo <= pending[1]:
            pending = (pending[0], max(pending[1], hi))
        else:
            if pending:
                yield pending
            pending = (lo, hi)
    if pending:
        yield pending


def registry_prefixes(registry):
    prefixes = {}
    for full in registry:
        for width in (2, 4, 6, 8):
            prefixes.setdefault(full[:width], []).append(full)
    return prefixes


def resolve_unique(prefixes, prefix):
    matches = prefixes.get(prefix, ())
    return matches[0] if len(matches) == 1 else None


def _summaries(source, work, key, registry, prefixes, start, end, diagnostics, result, bounds=None):
    where = 'WHERE at>=? AND at<?' if bounds is not None else ''
    with diagnostics.stage('neighbors'):
        edge_rows=list(work.execute(f'''SELECT verified,identity,direction,COUNT(*) AS receptions,
          COUNT(DISTINCT digest) AS unique_packets,MAX(at) AS last_observed
          FROM edges {where} GROUP BY verified,identity,direction
          ORDER BY receptions DESC,verified,identity,direction LIMIT 1000''', bounds or ()))
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
    with diagnostics.stage('neighbor_snr'):
        from meshcorestation.storage.neighbor_snr import summary
        quality={}
        result['neighbor_snr']=summary(source,registry,start,end,quality=quality)
        result['neighbor_snr_quality']=quality
        if quality['invalid_utc_records']:result['notes'].append('Saved firmware SNR records without valid UTC cannot be assigned to this observation period.')
        if quality['boundary_windows']:result['notes'].append('Firmware SNR windows crossing an observation boundary are excluded; samples cannot be split reliably.')
        if quality['partial_collections'] or quality['sequence_gaps'] or quality['reported_loss']:result['notes'].append('Firmware SNR collection includes partial cycles or cumulative retention diagnostics; review monitoring status.')



def _comparison_coverage(source, work, start, end, diagnostics, result):
    known = bool(source.execute("SELECT 1 FROM sqlite_master WHERE name='collection_windows'").fetchone())
    intervals = []
    seconds = 0
    for lo, hi in _coverage_intervals(source, start, end, diagnostics) if known else ():
        seconds += hi - lo
        if len(intervals) <= 10000:
            intervals.append((lo, hi))
    result.update(coverage_known=known, coverage_seconds=seconds)
    if len(intervals) > 10000:
        return
    if not intervals:
        result['covered_receptions'] = 0
        return
    starts = [lo for lo, _ in intervals]

    def recorded(at):
        i = bisect_right(starts, at) - 1
        return int(i >= 0 and at < intervals[i][1])

    work.create_function('recorded', 1, recorded, deterministic=True)
    result['covered_receptions'] = work.execute("""SELECT COUNT(*) FROM facts
        WHERE confirmed=1 AND at>=? AND at<? AND recorded(at)""", (start, end)).fetchone()[0]


def comparison_periods(main_path, key, source, registry, regions, windows, clock, diagnostics):
    """Classify the combined span once and summarize each half independently."""
    start, end = windows[0][0], min(clock, windows[-1][1])
    path = passive_stats.statistics_path(main_path, key)
    with closing(sqlite3.connect('')) as work:
        for connection in (source, work):
            connection.set_progress_handler(lambda: int(time.monotonic() >= diagnostics.deadline), 10000)
        with diagnostics.stage('classify'):
            prefixes = registry_prefixes(registry)
            marker = source_marker(source, path, key, registry, regions)
            routes = _spool(source, work, key, lambda prefix: resolve_unique(prefixes, prefix),
                            regions, start, end, diagnostics, main_path, marker)
        work.row_factory = sqlite3.Row
        result = []
        for lo, hi in windows:
            observed_end = min(clock, hi)
            bounds = lo, observed_end
            period = dict(start=lo, end=hi, future=hi>clock, coverage_expected=hi-lo,
                          totals={}, neighbors=[], neighbor_snr=[], ambiguous=[], notes=[])
            with diagnostics.stage('totals'):
                period['totals'] = dict(work.execute('SELECT '+COUNTS.replace('packet_digest','digest')+
                    ' FROM facts WHERE confirmed=1 AND at>=? AND at<?', bounds).fetchone())
            _summaries(source,work,key,registry,prefixes,*bounds,diagnostics,period,bounds=bounds)
            with diagnostics.stage('coverage'):
                _comparison_coverage(source, work, *bounds, diagnostics, period)
            result.append(period)
        return result, dict(diagnostics.report(), parsed_routes=routes.parsed, route_cache_bytes=routes.used)


def aggregate(main_path,key,days=1,now=None,start=None,end=None,_source=None,_metadata=None,_budget=None,_covered=False,_reuse=True):
    if days not in (1,7,30):raise ValueError('Choose 24 hours, 7 days or 30 days.')
    diagnostics=Diagnostics(QUERY_BUDGET_SECONDS if _budget is None else _budget)
    result=None;completed=False
    try:
        with diagnostics.stage('metadata'):
            status=passive_stats.snapshot(main_path,key)
            key=status['selected'];clock=time.time() if now is None else now
            now=clock if end is None else end;start=now-days*86400 if start is None else start
            if not all(type(v) in (int,float) and math.isfinite(v) for v in (start,now,clock)) or not 0<now-start<=30*86400:raise ValueError('Invalid historical window.')
            observed_end=min(now,clock)
            if _metadata is None:
                with closing(open_database(Path(main_path).as_uri()+'?mode=ro',timeout=.25)) as main:
                    registry={r['public_key']:dict(r) for r in main.execute('SELECT public_key,name,latitude,longitude FROM repeaters')}
                    regions=[dict(r) for r in main.execute('SELECT name,scope_key FROM statistics_regions UNION SELECT name,scope_key FROM scopes')]
            else:registry,regions=_metadata
            prefixes=registry_prefixes(registry)
            result=dict(ok=True,selected=key,days=days,start=start,end=now,generated_at=now,
                neighbor_snr=[],hourly=[],activity_hourly=[],packet_types=[],hops=[],regions=[],neighbors=[],ambiguous=[],totals={},excluded=0,
                future=now>clock,coverage_seconds=0,coverage_expected=now-start,coverage_known=False,
                selected_repeater=registry.get(key),notes=[])
            path=passive_stats.statistics_path(main_path,key) if key else None
            from meshcorestation.config import TIMEZONE
            local_bounds=_calendar_boundaries(start,now,TIMEZONE)
            result['activity_timezone']=TIMEZONE.key
            hourly={};activity={};coverage={};activity_coverage={}
        if path and path.exists():
            with (nullcontext(_source) if _source is not None else closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.25))) as source,closing(sqlite3.connect('')) as work:
                source.execute('PRAGMA query_only=ON')
                if _source is None:source.execute('BEGIN')
                source.set_progress_handler(lambda:int(time.monotonic()>=diagnostics.deadline),10000)
                work.set_progress_handler(lambda:int(time.monotonic()>=diagnostics.deadline),10000)
                with diagnostics.stage('classify'):
                    marker=source_marker(source,path,key,registry,regions) if _reuse else None
                    routes=_spool(source,work,key,lambda prefix: resolve_unique(prefixes,prefix),regions,start,observed_end,diagnostics,main_path,marker)
                work.row_factory=sqlite3.Row
                # Compact covering indexes, built only in this disposable spool.
                with diagnostics.stage('indexes'):
                    size=work.execute('PRAGMA page_count').fetchone()[0]*work.execute('PRAGMA page_size').fetchone()[0]
                    _space_guard(main_path,size*2)
                    work.executescript('''CREATE INDEX facts_confirmed_digest ON facts(confirmed,digest,at,id,hop);
                      CREATE INDEX edges_group ON edges(verified,identity,direction,digest,at);''')
                with diagnostics.stage('totals'):
                    result['totals']=dict(work.execute('SELECT '+COUNTS.replace('packet_digest','digest')+' FROM facts WHERE confirmed=1').fetchone())
                    result['excluded']=diagnostics.rows-result['totals']['receptions']
                count_sql=COUNTS.replace('packet_digest','digest')
                with diagnostics.stage('hourly'):
                    hourly={r['bucket']:dict(r) for r in work.execute('SELECT bucket,'+count_sql+' FROM facts WHERE confirmed=1 AND kind IN (2,5) GROUP BY bucket')}
                with diagnostics.stage('activity'):
                    # Reuse compact facts; never parse routes or read source payloads again.
                    bucket_sql = 'bucket'
                    if local_bounds[0] % 3600 or any(b-a != 3600 for a,b in zip(local_bounds,local_bounds[1:])):
                        work.create_function('calendar_bucket',1,lambda at:local_bounds[bisect_right(local_bounds,at)-1],deterministic=True)
                        bucket_sql = 'calendar_bucket(at)'
                    activity={r['bucket']:dict(r) for r in work.execute(
                        f'SELECT {bucket_sql} AS bucket,'+count_sql+f' FROM facts WHERE confirmed=1 AND origin=0 GROUP BY {bucket_sql}')}
                with diagnostics.stage('packet_types'):
                    result['packet_types']=[dict(r) for r in work.execute('''SELECT
                      kind AS packet_type,CAST(kind AS TEXT) AS category,
                      CASE WHEN origin=1 THEN 'advertisement-origin' ELSE 'observed-flood-route' END AS evidence,
                      '''+count_sql+''' FROM facts WHERE confirmed=1 OR origin=1
                      GROUP BY kind,evidence ORDER BY kind,evidence''')]
                    total=sum(r['receptions'] for r in result['packet_types'])
                    for row in result['packet_types']:row['percentage']=100*row['receptions']/total if total else 0
                with diagnostics.stage('hops'):
                    # The first confirmed reception in the selected period owns
                    # the unique packet, even if later copies have different hops.
                    # NULL digests remain unidentified, never one shared packet.
                    result['hops']=[dict(r) for r in work.execute("""
                      WITH classified AS (
                        SELECT hop,digest,CASE WHEN digest IS NOT NULL AND ROW_NUMBER() OVER (
                          PARTITION BY digest ORDER BY at,id)=1 THEN 1 ELSE 0 END AS first_seen
                        FROM facts WHERE confirmed=1)
                      SELECT hop AS hop_count,COUNT(*) AS receptions,
                        SUM(first_seen) AS unique_packets,
                        COUNT(digest)-SUM(first_seen) AS repeated,
                        COUNT(*)-COUNT(digest) AS unidentified
                      FROM classified GROUP BY hop ORDER BY hop""")]
                with diagnostics.stage('regions'):
                    result['regions']=[dict(r) for r in work.execute('SELECT region AS name,'+count_sql+' FROM facts WHERE confirmed=1 GROUP BY region ORDER BY receptions DESC,region')]
                    for row in result['regions']:row['percentage']=100*row['receptions']/result['totals']['receptions'] if result['totals']['receptions'] else 0
                _summaries(source,work,key,registry,prefixes,start,observed_end,diagnostics,result)
                with diagnostics.stage('coverage'):
                    coverage,result['coverage_known'],activity_coverage=_coverage(source,start,observed_end,diagnostics,local_bounds)
                if _covered:
                    with diagnostics.stage('covered_traffic'):
                        intervals=[]
                        if source.execute("SELECT 1 FROM sqlite_master WHERE name='collection_windows'").fetchone():
                            for lo,hi in source.execute('SELECT started_at,ended_at FROM collection_windows WHERE ended_at>? AND started_at<? ORDER BY started_at',(start,observed_end)):
                                diagnostics.check();lo=max(start,lo);hi=min(observed_end,hi)
                                if intervals and lo<=intervals[-1][1]:intervals[-1]=(intervals[-1][0],max(hi,intervals[-1][1]))
                                else:intervals.append((lo,hi))
                                if len(intervals)>10000:intervals=None;break
                        if intervals is not None:
                            starts=[r[0] for r in intervals]
                            def covered(at):
                                i=bisect_right(starts,at)-1
                                return int(i>=0 and at<intervals[i][1])
                            work.create_function('recorded',1,covered,deterministic=True)
                            result['covered_receptions']=work.execute('SELECT COUNT(*) FROM facts WHERE confirmed=1 AND recorded(at)').fetchone()[0]
                result['diagnostics']=dict(source_rows=diagnostics.rows,classified_rows=diagnostics.classified,parsed_routes=routes.parsed,route_cache_bytes=routes.used)
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
            result['notes'].append('Hop ranking classifies the first confirmed reception per digest across the selected period as unique and later copies as repeated, at their recorded hop counts. Hourly and regional unique counts are deduplicated within each hour or region.')
        result.setdefault('diagnostics',{})['stages_ms']=diagnostics.times
        completed=True
        return result
    finally:
        (LOGGER.info if completed else LOGGER.warning)('Statistics aggregation outcome=%s rows=%d total_ms=%.3f stages_ms=%s','complete' if completed else 'failed',diagnostics.rows,(time.monotonic()-diagnostics.started)*1000,diagnostics.times)
