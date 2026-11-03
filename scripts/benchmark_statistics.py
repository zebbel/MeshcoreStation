"""Reproducible saved-view workload; synthetic DBs only, no radio/network.

Run with --output outside the checkout. --module may point to a saved baseline
statistics_view.py. All observations are within 24h to stress every filter equally.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import importlib.util
import json
import logging
from pathlib import Path
import resource
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace as NS
from meshcorestation.storage import database,passive_stats,voltage_store

KEY='aa11'+'01'*30
NOW=1800000000.0


def create_fixture(directory,count):
    path=Path(directory)/'meshcorestation.db'
    old=database.DB_FILE;database.DB_FILE=path
    try:owner=database.Database(logging.getLogger('benchmark'))
    finally:database.DB_FILE=old
    keys=[KEY]+[hashlib.sha256(('synthetic-repeater-'+str(i)).encode()).hexdigest() for i in range(256)]
    for index,key in enumerate(keys):owner.add_new_repeater(NS(payload=dict(type=2,public_key=key,adv_name=f'Synthetic {index}',adv_lat=49+index/10000,adv_lon=8+index/10000)),observed=False)
    with owner.db:
        voltage_store.ensure_repeater(owner.db,KEY)
        owner.db.execute('UPDATE voltage_config SET statistics_since_ns=0 WHERE public_key=?',(KEY,))
        owner.db.executemany('INSERT INTO statistics_regions VALUES(?,?)',[(f'region-{i}',hashlib.sha256(f'#region-{i}'.encode()).digest()[:16].hex()) for i in range(8)])
    rows=[];templates=[]
    for i in range(512):
        route=[keys[1+(i*j+11*j)%256][:4] for j in range(1,5+i%13)]
        route.insert(i%len(route),KEY[:4])
        if i%31==0:route.append(KEY[:4])
        packet=passive_stats.normalize(dict(payload_type=5,route_type=1,path_hash_size=2,path_len=len(route),path=''.join(route),pkt_payload=b'fixture'))
        attr=next(v for k,v in passive_stats.attribute(packet,set(keys),{KEY}) if k==KEY)
        templates.append((packet,attr))
    start=time.perf_counter()
    for i in range(count):
        packet,attr=templates[i%512];at=NOW-1-(i*7919)%86000
        kind=[5,2,6,4,3][i%5];route_type=2 if i%23==0 else 0 if i%2 else 1
        payload=hashlib.sha256(str(i//3).encode()).digest()*3
        key=hashlib.sha256(f'#region-{i%8}'.encode()).digest()[:16]
        code=int.from_bytes(hmac.new(key,bytes([kind])+payload,hashlib.sha256).digest()[:2],'little');code=1 if code==0 else 65534 if code==65535 else code
        transport=(code.to_bytes(2,'little')+b'\x12\x34').hex() if route_type==0 else None
        j=lambda v:json.dumps(v,separators=(',',':'))
        rows.append((f'synthetic-{i}',at,at,kind,route_type,int(route_type==0),transport,payload,None,
            hashlib.sha256(bytes([kind])+payload).hexdigest(),None,j({'synthetic':True,'extra':'x'*800}),-98,2.5,
            packet['count'],packet['size'],packet['path_raw'],j(attr['route']),j(attr['positions']),
            attr['first_hop'],attr['middle_hop'],attr['last_hop'],j(attr['previous']),j(attr['following']),
            'ambiguous' if i%37==0 else attr['confidence'],int(i%37==0),attr['evidence'],at))
        if len(rows)>=2500:passive_stats._write(passive_stats.statistics_path(path,KEY),rows);rows=[]
    if rows:passive_stats._write(passive_stats.statistics_path(path,KEY),rows)
    owner.close()
    return path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sizes',default='2500,10000,50000,100000');parser.add_argument('--periods',default='1,7,30');parser.add_argument('--repeats',type=int,default=2);parser.add_argument('--module');parser.add_argument('--output',required=True);parser.add_argument('--profile',action='store_true');args=parser.parse_args()
    if args.module:
        spec=importlib.util.spec_from_file_location('benchmark_view',args.module);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    else:from meshcorestation.storage import statistics_view as module
    report=[]
    for count in map(int,args.sizes.split(',')):
        with tempfile.TemporaryDirectory(prefix='statistics-benchmark-',dir=Path(args.output).resolve().parent) as directory:
            path=create_fixture(directory,count)
            for days in map(int,args.periods.split(',')):
                for repeat in range(args.repeats):
                    wall=time.perf_counter();cpu=time.process_time();result=None;error=None
                    try:
                        if args.profile:
                            import cProfile
                            profiler=cProfile.Profile();result=profiler.runcall(module.aggregate,path,KEY,days,now=NOW)
                            profiler.dump_stats(args.output+f'.{count}.{days}.{repeat}.profile')
                        else:result=module.aggregate(path,KEY,days,now=NOW)
                    except Exception as exc:error=type(exc).__name__+': '+str(exc)
                    row=dict(observations=count,days=days,repeat=repeat,wall_seconds=round(time.perf_counter()-wall,4),cpu_seconds=round(time.process_time()-cpu,4),peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,error=error,confirmed=result['totals'].get('receptions') if result else None)
                    row['diagnostics']=result.get('diagnostics',{}) if result else {}
                    report.append(row);print(json.dumps({k:v for k,v in row.items() if k!='diagnostics'}),flush=True)
                    Path(args.output).write_text(json.dumps(report,indent=2))
    return report

if __name__=='__main__':main()
