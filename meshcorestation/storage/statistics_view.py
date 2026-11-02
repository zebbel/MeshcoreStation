"""SQLite aggregates of saved passive evidence; no radio/network calls."""
from contextlib import closing
from functools import lru_cache
import hashlib
import hmac
import json
import math
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


def aggregate(main_path,key,days=1,now=None):
    if days not in (1,7,30):raise ValueError('Choose 24 hours, 7 days or 30 days.')
    status=passive_stats.snapshot(main_path,key)
    key=status['selected'];now=time.time() if now is None else now;start=now-days*86400
    with closing(open_database(Path(main_path).as_uri()+'?mode=ro',timeout=2)) as main:
        registry={r['public_key']:dict(r) for r in main.execute('SELECT public_key,name,latitude,longitude FROM repeaters')}
        regions=[dict(r) for r in main.execute('SELECT name,scope_key FROM statistics_regions UNION SELECT name,scope_key FROM scopes')]
    prefixes={}
    for full in registry:
        for width in (2,4,6,8):prefixes.setdefault(full[:width],[]).append(full)
    def resolve_hash(prefix):
        matches=prefixes.get(prefix,[])
        return matches[0] if len(matches)==1 else None
    @lru_cache(maxsize=256)
    def selected_confirmed(route):
        try:return int(any(h.get('status')=='matched' and resolve_hash(h.get('hash'))==key for h in json.loads(route)))
        except (ValueError,TypeError,AttributeError):return 0
    result=dict(ok=True,selected=key,days=days,start=start,end=now,generated_at=now,
                hourly=[],hops=[],regions=[],neighbors=[],ambiguous=[],totals={},excluded=0,
                coverage_seconds=0,coverage_expected=days*86400,coverage_known=False,
                selected_repeater=registry.get(key),notes=[])
    path=passive_stats.statistics_path(main_path,key) if key else None
    hourly={};coverage=[]
    if path and path.exists():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            deadline=time.monotonic()+8
            db.set_progress_handler(lambda:int(time.monotonic()>deadline),10000)
            db.create_function('selected_confirmed',1,selected_confirmed,deterministic=True)
            db.create_function('resolve_hash',1,resolve_hash,deterministic=True)
            db.create_function('region_name',4,scope_resolver(regions),deterministic=True)
            # Use a temp CTE, not an index-dependent full history export. Timestamp
            # predicates use the existing per-repeater index before JSON processing.
            base='''WITH window AS (SELECT * FROM observations WHERE received_at>=? AND received_at<?),
              confirmed AS (SELECT * FROM window WHERE route_type IN (0,1) AND packet_type!=9
              AND ambiguous=0 AND (first_hop=1 OR middle_hop=1 OR last_hop=1) AND selected_confirmed(route)=1) '''
            args=(start,now)
            result['totals']=dict(db.execute(base+'SELECT '+COUNTS+' FROM confirmed',args).fetchone())
            all_count=db.execute('SELECT COUNT(*) FROM observations WHERE received_at>=? AND received_at<?',args).fetchone()[0]
            result['excluded']=all_count-result['totals']['receptions']
            hourly={r['bucket']:dict(r) for r in db.execute(base+'''SELECT CAST(received_at/3600 AS INTEGER)*3600 AS bucket,
                '''+COUNTS+''' FROM confirmed WHERE packet_type IN (2,5) GROUP BY bucket''',args)}
            result['hops']=[dict(r) for r in db.execute(base+'SELECT hop_count,'+COUNTS+' FROM confirmed GROUP BY hop_count ORDER BY receptions DESC,hop_count',args)]
            result['regions']=[dict(r) for r in db.execute(base+'''SELECT region_name(packet_type,payload,transport_code,route_type) AS name,
                '''+COUNTS+''' FROM confirmed GROUP BY name ORDER BY receptions DESC,name''',args)]
            for row in result['regions']:
                row['percentage']=100*row['receptions']/result['totals']['receptions'] if result['totals']['receptions'] else 0
            # Adjacent hash pairs around the selected repeater only. DISTINCT keeps
            # a repeated target in a route from double-counting a direction/reception.
            edge_sql='''WITH window AS (SELECT * FROM observations WHERE received_at>=? AND received_at<?
                AND route_type IN (0,1) AND packet_type!=9), targets AS (
                SELECT o.*,a.value AS target,CAST(a.key AS INTEGER) AS target_index
                FROM window o,json_each(o.route) a
                WHERE json_extract(a.value,'$.hash')=substr(?,1,length(json_extract(a.value,'$.hash')))), pairs AS (
                SELECT DISTINCT reception_id,packet_digest,received_at,ambiguous,target,
                  json_extract(route,'$['||(target_index+offset)||']') AS neighbor,
                  CASE WHEN offset=1 THEN 'outgoing' ELSE 'incoming' END AS direction
                FROM targets CROSS JOIN (SELECT -1 AS offset UNION ALL SELECT 1)
                WHERE target_index+offset>=0 AND target_index+offset<json_array_length(route)), edges AS (
                SELECT *,resolve_hash(json_extract(neighbor,'$.hash')) AS neighbor_key,
                  CASE WHEN ambiguous=0 AND json_extract(target,'$.status')='matched'
                    AND json_extract(neighbor,'$.status')='matched'
                    AND resolve_hash(json_extract(target,'$.hash'))=?
                    AND resolve_hash(json_extract(neighbor,'$.hash')) IS NOT NULL THEN 1 ELSE 0 END AS verified
                FROM pairs)
                SELECT verified,CASE WHEN verified=1 THEN neighbor_key ELSE json_extract(target,'$.hash')||' → '||json_extract(neighbor,'$.hash') END AS identity,
                direction,COUNT(*) AS receptions,COUNT(DISTINCT packet_digest) AS unique_packets,
                MAX(received_at) AS last_observed FROM edges GROUP BY verified,identity,direction
                ORDER BY receptions DESC LIMIT 1000'''
            grouped={};ambiguous=[]
            edge_rows=list(db.execute(edge_sql,(*args,key,key)))
            for r in edge_rows:
                r=dict(r)
                if not r['verified']:
                    r['candidates']=prefixes.get(r['identity'].split(' → ')[-1],[])
                    ambiguous.append(r);continue
                if r['identity']==key:continue
                item=grouped.setdefault(r['identity'],dict(registry[r['identity']],incoming=0,outgoing=0,last_observed=0))
                item[r['direction']]=r['receptions'];item[r['direction']+'_unique']=r['unique_packets']
                item['last_observed']=max(item['last_observed'],r['last_observed'])
            result['neighbors']=list(grouped.values());result['ambiguous']=ambiguous
            if len(edge_rows)>=1000:result['notes'].append('Neighbor output is limited to 1,000 grouped direction entries.')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='collection_windows'").fetchone():
                coverage=[tuple(r) for r in db.execute('SELECT started_at,ended_at FROM collection_windows WHERE ended_at>? AND started_at<? ORDER BY started_at',args)]
                result['coverage_known']=True
    merged=[]
    for lo,hi in coverage:
        if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],hi))
        else:merged.append((lo,hi))
    coverage=merged
    # Only coverage intervals prove recorded uptime; existing 5.1.0 history has none.
    for bucket in range(int(start//3600)*3600,int(now//3600)*3600+1,3600):
        lo,hi=max(start,bucket),min(now,bucket+3600)
        if hi<=lo:continue
        seconds=sum(max(0,min(hi,b)-max(lo,a)) for a,b in coverage)
        seconds=min(hi-lo,seconds);result['coverage_seconds']+=seconds
        values=hourly.get(bucket)
        result['hourly'].append(dict(at=bucket,coverage_seconds=seconds,expected_seconds=hi-lo,
            complete=seconds>=hi-lo-1e-6,**(values if values else dict(receptions=0 if seconds>=hi-lo-1e-6 else None,
                unique_packets=0 if seconds>=hi-lo-1e-6 else None,repeated=0 if seconds>=hi-lo-1e-6 else None,unidentified=0 if seconds>=hi-lo-1e-6 else None))))
    result['notes'].append('Adjacent flood-path observations are inferred relationships, not verified direct RF links or delivery confirmation.')
    result['notes'].append('Unique packets are distinct payload digests within each hour or ranking category; repeated receptions are additional copies in that group.')
    return result
