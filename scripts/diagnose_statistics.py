"""Read-only saved-data diagnostics for V5 5.2.1; no radio/network calls.

Can be downloaded and run from the installation directory with PYTHONPATH=.
Reports counts/timing only, never payloads, routes, names or scope keys. The
existing view may use disposable SQLite scratch; original observations are read-only.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import platform
import resource
import shlex
import sqlite3
import time


def environment_data_directory():
    """Read only the data-directory preference as data, never source an env file."""
    if 'MESHCORESTATION_DATA_DIR' in os.environ:return
    path=Path('meshcorestation.env')
    if not path.exists():return
    for line in path.read_text().splitlines():
        name,separator,value=line.partition('=')
        if separator and name.strip()=='MESHCORESTATION_DATA_DIR':
            parsed=shlex.split(value,comments=True)
            if len(parsed)==1:os.environ[name.strip()]=parsed[0]
            return


class Profile:
    def __init__(self):self.seconds={};self.calls={};self.rows=0;self.parsed=0;self.max_route_bytes=0

    def measure(self,name,fn,*args,**kwargs):
        started=time.perf_counter()
        try:return fn(*args,**kwargs)
        finally:
            self.seconds[name]=self.seconds.get(name,0)+time.perf_counter()-started
            self.calls[name]=self.calls.get(name,0)+1


class Cursor:
    def __init__(self,cursor,profile):self.cursor,self.profile=cursor,profile
    def fetchmany(self,*args):
        rows=self.profile.measure('source_fetch',self.cursor.fetchmany,*args)
        self.profile.rows+=len(rows);return rows
    def __getattr__(self,name):return getattr(self.cursor,name)


class Connection:
    def __init__(self,db,profile,kind):self.db,self.profile,self.kind=db,profile,kind
    def execute(self,*args):
        cursor=self.profile.measure(self.kind+'_execute',self.db.execute,*args)
        return Cursor(cursor,self.profile) if self.kind=='source' else cursor
    def executescript(self,*args):return self.profile.measure(self.kind+'_setup',self.db.executescript,*args)
    def executemany(self,*args):return self.profile.measure(self.kind+'_insert',self.db.executemany,*args)
    def __getattr__(self,name):return getattr(self.db,name)


def profile_actual(main_path,key,days,*,now=None,reuse=False):
    from meshcorestation.storage import statistics_view as module
    profile=Profile()
    original_scope,original_route,original_guard,original_spool=module.scope_resolver,module.RouteCache.get,module._space_guard,module._spool
    def scope(regions):
        fn=original_scope(regions)
        return lambda *args:profile.measure('scope_matching',fn,*args)
    def route(cache,value):
        before=cache.parsed;profile.max_route_bytes=max(profile.max_route_bytes,len(value.encode('utf-8')))
        try:return profile.measure('route_resolution',original_route,cache,value)
        finally:profile.parsed+=cache.parsed-before
    def guard(*args):return profile.measure('space_checks',original_guard,*args)
    def spool(source,work,*args):return original_spool(Connection(source,profile,'source'),Connection(work,profile,'scratch'),*args)
    module.scope_resolver,module.RouteCache.get,module._space_guard,module._spool=scope,route,guard,spool
    wall,cpu=time.perf_counter(),time.process_time();value=None;error=None;failed_diagnostics={}
    try:value=module.aggregate(main_path,key,days,now=now,_reuse=reuse)
    except Exception as exc:
        # Do not echo a malformed stored value in an exception message.
        error=dict(type=type(exc).__name__,stage=getattr(exc,'stage',None))
        failed_diagnostics=getattr(exc,'diagnostics',{})
    finally:module.scope_resolver,module.RouteCache.get,module._space_guard,module._spool=original_scope,original_route,original_guard,original_spool
    return dict(wall_seconds=round(time.perf_counter()-wall,4),cpu_seconds=round(time.process_time()-cpu,4),
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,error=error,
                fetched_rows=profile.rows,parsed_routes=profile.parsed,max_profiled_route_bytes=profile.max_route_bytes,
                breakdown_ms={name:round(value*1000,3) for name,value in profile.seconds.items()},calls=profile.calls,
                diagnostics=value.get('diagnostics',{}) if value else failed_diagnostics)


def inspect(main_path,selection=None,days=1,*,reuse=False):
    from meshcorestation.storage.connection import connect
    from meshcorestation.storage.passive_stats import snapshot,statistics_path
    from meshcorestation import __version__
    main_path=Path(main_path).resolve()
    if not main_path.exists() or not main_path.with_name('knownRepeaters.db').exists():
        raise ValueError('Main/known repeater databases not found. Run from the installation directory or pass --database.')
    status=snapshot(main_path)
    repeaters=status['repeaters']
    choices=[dict(selection=i+1,key_prefix=r['public_key'][:12]) for i,r in enumerate(repeaters)]
    if not repeaters:raise ValueError('No managed repeaters.')
    if selection is None and len(repeaters)>1:return dict(selection_required=True,managed_repeaters=choices)
    index=(selection or 1)-1
    if not 0<=index<len(repeaters):raise ValueError('Choose one of the numbered managed repeaters.')
    key=repeaters[index]['public_key'];status=snapshot(main_path,key)
    with closing(connect(main_path.as_uri()+'?mode=ro',timeout=.25)) as main:
        metadata=dict(known_repeaters=main.execute('SELECT COUNT(*) FROM repeaters').fetchone()[0],
                      configured_regions=main.execute('SELECT COUNT(*) FROM statistics_regions').fetchone()[0],
                      saved_reply_scopes=main.execute('SELECT COUNT(*) FROM scopes').fetchone()[0],
                      distinct_region_keys=main.execute('SELECT COUNT(DISTINCT scope_key) FROM (SELECT scope_key FROM statistics_regions UNION ALL SELECT scope_key FROM scopes)').fetchone()[0])
    source=statistics_path(main_path,key)
    result=dict(version=__version__,machine=platform.machine(),cpu_count=os.cpu_count(),days=days,
                selected_prefix=key[:12],saved_count=status['observation_count'],configuration=metadata)
    if not source.exists():return dict(result,error='No saved statistics file.')
    result['storage_bytes']=source.stat().st_size
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=.25)) as db:
        deadline=time.monotonic()+2;db.set_progress_handler(lambda:int(time.monotonic()>deadline),10000)
        try:
            row=db.execute('''SELECT COUNT(*),AVG(LENGTH(route)),MAX(LENGTH(route)),AVG(hop_count),
                SUM(route_type=0),SUM(ambiguous!=0) FROM observations WHERE received_at>=? AND received_at<?''',
                (time.time()-days*86400,time.time())).fetchone()
            result['window']=dict(rows=row[0],mean_route_bytes=round(row[1] or 0,1),max_route_bytes=row[2],mean_hops=round(row[3] or 0,2),scoped_rows=row[4],ambiguous_rows=row[5])
        except sqlite3.Error:result['window']=dict(error='Summary query unavailable within two seconds.')
    result['profile']=profile_actual(main_path,key,days,reuse=reuse)
    return result


def main():
    environment_data_directory()
    from meshcorestation.config import DB_PATH
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=DB_PATH)
    parser.add_argument('--repeater',type=int,help='Number from the selection list when multiple repeaters are managed.')
    parser.add_argument('--days',type=int,choices=[1,7,30],default=1)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--reuse-classification',action='store_true',
                        help='Exercise the disposable classification cache; source history remains read-only.')
    args=parser.parse_args()
    try:result=inspect(args.database,args.repeater,args.days,reuse=args.reuse_classification)
    except (ValueError,OSError,sqlite3.Error) as exc:result=dict(error=type(exc).__name__,note='Check the installation directory, --database path and selected repeater.')
    encoded=json.dumps(result,indent=2)
    print(encoded)
    if args.output:args.output.write_text(encoded+'\n')


if __name__=='__main__':main()
