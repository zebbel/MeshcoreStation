"""Disposable local HTTP app for browser regressions; never starts a radio."""
import logging
import tempfile
import os
from pathlib import Path

# Before any application imports, keep every database outside the checkout.
with tempfile.TemporaryDirectory(prefix='meshcorestation-browser-') as directory:
    os.environ['MESHCORESTATION_DATA_DIR']=directory
    from meshcorestation.storage.database import Database
    from meshcorestation.storage import voltage_store, passive_stats
    from meshcorestation.web.app import create_app
    key='769b90b4dd327d7bc9cc651fb8d2f8a4a217957cd36feac6b3216b5acedc36ff'
    other='ab'*32
    owner=Database(logging.getLogger('browser-test'));voltage_store.initialize(owner.db)
    with owner.db:
        for public_key,name in ((key,'DE_HE_HP_RPT1'),(other,'Second Repeater')):
            owner.db.execute('INSERT INTO repeaters(public_key,name,adv_type,first_seen,last_seen) VALUES (?,?,2,0,0)',(public_key,name))
            voltage_store.ensure_repeater(owner.db,public_key)
    owner.close();passive_stats.initialize();passive_stats.track(key);passive_stats.track(other)
    # Historical, synthetic local observations and real Analyzer response shapes.
    # This disposable test app has no companion/radio worker or external caller.
    import time, json, copy
    from datetime import datetime, timezone
    from contextlib import closing
    from meshcorestation.storage import performance_store, optimizer_store, advisor_history
    optimizer_store.initialize()
    now=time.time()
    root=Path('tests/fixtures/analyzer/responses')
    sample={name:json.loads((root/file).read_text()) for name,file in {
        'detail':'node_detail_24h.json','reach':'node_reach_1d.json','metrics':'graph_metrics.json'}.items()}
    for hour in range(0,31*24,6):
        if 72<hour<96: continue # An intentional observation gap.
        at=now-hour*3600
        snapshot=copy.deepcopy(sample)
        snapshot['detail']['stat'].update(pairsServed=31 if hour<48 else 21,pairsSole=2 if hour<48 else 1)
        end=int(at//3600)*3600
        snapshot['detail']['relayTimeline']=[{'bucket':datetime.fromtimestamp(h,timezone.utc).isoformat(),'count':5 if hour<48 else 3} for h in range(end-24*3600,end,3600) if not 72<(now-h)/3600<96]
        performance_store.record_analyzer(key,at,snapshot)
    with performance_store.database() as db:
        db.execute("INSERT INTO collection_schedule VALUES(?,?,?,?,?,?)",(key,now+43200,now,now,'available',None))
    with closing(passive_stats.connect()) as db,db:
        for hour in range(31*24):
            if 72<hour<96: continue
            at=now-hour*3600-10
            for i in range(1 if hour>48 else 2):
                route=json.dumps([{'key':key,'name':'DE_HE_HP_RPT1','status':'matched'}])
                db.execute("INSERT INTO observations(target,at,digest,kind,scoped,ambiguous,first_hop,middle_hop,last_hop,route,previous,following) VALUES(?,?,?,5,1,0,1,0,0,?,'[]','[]')",(key,at,'payload-'+str(hour)+'-'+str(i),route))
                db.execute('INSERT INTO network_observations(at,kind,scoped,path_len,hash_size,route,digest) VALUES(?,5,1,1,1,?,?)',(at,key[:2],'payload-'+str(hour)+'-'+str(i)))
        for hour in range(31*24):
            if 72<hour<96: continue
            at=now-hour*3600-10
            for i in range(3):
                db.execute('INSERT INTO network_observations(at,kind,scoped,path_len,hash_size,route,digest) VALUES(?,5,1,1,1,?,?)',(at,other[:2],'other-'+str(hour)+'-'+str(i)))
    performance_store.marker_change(key,'create',{'description':'Fixture antenna replacement','at':now-2*86400})
    with advisor_history.database() as db:
        db.execute("INSERT INTO changes VALUES(12345,?,?,'flood.max','10','8','8','verified')",(now-2*86400+3600,key))
    # A complete successful saved response powers Performance's cache-only map.
    from meshcorestation.analyzer import service
    cached=dict(sample)
    for name,file in {'neighbors':'node_neighbors.json','clock':'clock_skew_24h.json','direct':'direct_packets_24h_empty.json','beacons':'channel_beacons_720h_empty.json','sensors':'channel_sensors_720h_empty.json'}.items():
        cached[name]=json.loads((root/file).read_text())
    cached['detail']['stat'].update(pairsServed=31,pairsSole=2)
    with service.connection() as db:
        db.execute('INSERT OR REPLACE INTO analyzer_cache VALUES(?,?,?,?)',(key,now,json.dumps(cached),'{}'))
    create_app().server.run(host='127.0.0.1',port=8050,debug=False,use_reloader=False)
