"""Read-only dashboard projections. Sources stay separate; gaps stay unknown."""
from contextlib import closing
import math
import sqlite3
from meshcorestation.storage import performance_store as store, passive_stats

HOUR=3600
SNAPSHOT_STEP=12*HOUR


def comparable_companion(key,start,end,step):
    """Both counts from the SAME network_observations rows, never tracked copies.

    A zero means no collision-checked matching paths among received rows, not
    proven zero forwarding. Ambiguous paths invalidate the involvement bucket.
    Empty/partial buckets cannot become an indexed baseline.
    """
    first=int(start//step)*step
    bins={at:{'at':at,'stamp':at+step/2,'copies':None,'network':None,'ambiguous':None,
              'complete':at>=start and at+step<=end,'repeater_index':None,'mesh_index':None}
          for at in range(first,math.ceil(end/step)*step,step)}
    result={'timeline':list(bins.values()),'baseline':None,'source':'Companion network path observations',
            'error':None,'available':0,'expected':sum(b['complete'] for b in bins.values())}
    if not passive_stats.STATS_PATH.exists():
        return result
    try:
        keys={r['public_key'] for r in passive_stats.known_repeaters()}|{key}
        good,bad=[],[]
        for size in (1,2,3):
            (bad if sum(k.startswith(key[:2*size]) for k in keys)>1 else good).append((size,'%|'+key[:2*size]+'|%'))
        def condition(parts):
            return ' OR '.join("(hash_size=? AND ('|'||route||'|') LIKE ?)" for _ in parts) or '0'
        def args(parts):return [v for pair in parts for v in pair]
        with closing(passive_stats.connect()) as db:
            rows=db.execute(f'''SELECT CAST(at/? AS INTEGER)*?,COUNT(*),
                SUM(CASE WHEN {condition(good)} THEN 1 ELSE 0 END),
                SUM(CASE WHEN {condition(bad)} THEN 1 ELSE 0 END)
                FROM network_observations WHERE at>=? AND at<? GROUP BY 1''',
                (step,step,*args(good),*args(bad),start,end)).fetchall()
            health=db.execute('SELECT error,trimmed_at FROM health WHERE id=1').fetchone()
        for at,total,involved,ambiguous in rows:
            bins[at].update(network=total,copies=involved if not ambiguous else None,ambiguous=ambiguous)
        if health:
            result['error']=health[0] or None
            result['trimmed_at']=health[1]
    except (OSError,sqlite3.Error):
        result['error']='Comparable Companion history unavailable.'
        return result
    baseline=next((b for b in bins.values() if b['complete'] and b['copies'] and b['network']),None)
    if baseline:
        result['baseline']={'at':baseline['at'],'copies':baseline['copies'],'network':baseline['network']}
        for b in bins.values():
            if b['at']>=baseline['at'] and b['complete'] and b['copies'] is not None and b['network'] is not None:
                b['repeater_index']=100*b['copies']/baseline['copies']
                b['mesh_index']=100*b['network']/baseline['network']
    result['available']=sum(b['complete'] and b['copies'] is not None and b['network'] is not None for b in bins.values())
    return result


def snapshot_series(key,start,end,now):
    bins=[{'at':start+i*SNAPSHOT_STEP,'stamp':None,'neighbors':None,'two_way':None,'pairs':None,'sole_pairs':None}
          for i in range(math.ceil((end-start)/SNAPSHOT_STEP))]
    with store.database() as db:
        rows=db.execute('''SELECT m.at,m.neighbors,m.two_way,d.pairs,d.sole_pairs
            FROM measurements m LEFT JOIN measurement_details d ON d.public_key=m.public_key AND d.at=m.at
            WHERE m.public_key=? AND m.at>=? AND m.at<? ORDER BY m.at''',(key,start,min(now,end))).fetchall()
    for row in rows:
        i=min(len(bins)-1,int((row['at']-start)//SNAPSHOT_STEP))
        if i>=0:
            bins[i].update(dict(row));bins[i]['stamp']=row['at'];bins[i]['at']=start+i*SNAPSHOT_STEP
    return bins


def measured_change(before,after):
    return {'before':before,'after':after,'difference':after-before,
            'percent':100*(after-before)/before if before else None}


def assess(series,fields,start,end,split,step,now,kind):
    expected=[max(0,int(math.floor((stop-begin)/step))) for begin,stop in ((start,split),(split,end))]
    groups=[[r for r in series if begin<=r['at'] and r['at']+step<=stop and all(r.get(f) is not None for f in fields)]
            for begin,stop in ((start,split),(split,end))]
    coverage={'available':[len(g) for g in groups],'expected':expected}
    result={'status':'Insufficient Data','coverage':coverage,'changes':{},'explanation':'Missing or partial observations prevent a supported comparison.'}
    if end>now or not all(expected) or any(len(g)!=n for g,n in zip(groups,expected)):
        return result
    result['status']='Observed change'
    for f in fields:
        values=[sum(r[f] for r in g)/len(g) for g in groups]
        result['changes'][f]=measured_change(*values)
    if kind=='companion':
        involvement,mesh=(result['changes'][f] for f in fields)
        if involvement['percent'] is None or mesh['percent'] is None:
            result.update(status='Insufficient Data',explanation='A zero baseline prevents a relative activity comparison; recorded counts remain available.')
        else:
            delta=involvement['percent']-mesh['percent']
            if abs(delta)<.01: direction='at the same rate as'
            elif involvement['percent']<0 and mesh['percent']<0: direction='with a slower decline than' if delta>0 else 'with a faster decline than'
            else: direction='faster than' if delta>0 else 'slower than'
            result['explanation']=f"Repeater involvement changed {direction} Companion-observed mesh traffic ({involvement['percent']:+.1f}% versus {mesh['percent']:+.1f}%). This is relative observed involvement, not evidence of delivery success or a cause."
    else:
        result['explanation']='Changes compare mean observed values in equal periods. Higher activity or inferred connectivity alone does not establish better delivery.'
    return result


def dashboard(key,start,end,step,now=None,split=None):
    now=end if now is None else now
    split=(start+end)/2 if split is None else split
    # Align Companion and hourly assessment halves to complete source buckets.
    # The marker comparison keeps its exact boundary and excludes straddling bins.
    hours=store.hourly(key,start,min(end,now))
    counts={r['at']:r['count'] for r in hours}
    forwarding=[{'at':h,'stamp':h,'hourly_relays':counts.get(h)} for h in range(math.ceil(start/HOUR)*HOUR,int(end//HOUR)*HOUR,HOUR)]
    companion=comparable_companion(key,start,min(now,end),step)
    snapshots=snapshot_series(key,start,end,now)
    assessment={
        'forwarding':assess(forwarding,['hourly_relays'],start,end,split,HOUR,now,'forwarding'),
        'relative':assess(companion['timeline'],['copies','network'],start,end,split,step,now,'companion'),
        'connectivity':assess(snapshots,['neighbors','two_way'],start,end,split,SNAPSHOT_STEP,now,'connectivity'),
        'routing':assess(snapshots,['pairs','sole_pairs'],start,end,split,SNAPSHOT_STEP,now,'routing')}
    # Partial first/last UTC hours or Companion buckets are excluded from both
    # expected and available counts. Equal halves have equal contained durations.
    for name,series,fields,size in [('forwarding',forwarding,['hourly_relays'],HOUR),('relative',companion['timeline'],['copies','network'],step)]:
        groups=[];expected=[]
        for begin,stop in ((start,split),(split,end)):
            first=math.ceil(begin/size)*size
            expected.append(max(0,int((math.floor(stop/size)*size-first)//size)))
            groups.append([r for r in series if r['at']>=first and r['at']+size<=stop])
        # assess uses durations for expected; provide equivalent aligned bounds.
        # Missing rows remain represented by null buckets. Complete equal aligned
        # halves have the same count for supported 24h/7d/30d and marker windows.
        count=min(expected)
        if count:
            selected=[g[-count:] for g in groups]
            projected=[{**r,'at':i*count*size+j*size} for i,g in enumerate(selected) for j,r in enumerate(g)]
            assessment[name]=assess(projected,fields,0,2*count*size,count*size,size,2*count*size if end<=now else -1,'companion' if name=='relative' else name)
        else:
            assessment[name]['coverage']={'available':[0,0],'expected':expected}
    if companion.get('error') or (companion.get('trimmed_at') and companion['trimmed_at']>=start):
        assessment['relative'].update(status='Insufficient Data',explanation='Companion collection or retention warnings prevent a supported relative comparison.')
    with store.database() as db:
        latest=db.execute('''SELECT m.*,d.pairs,d.sole_pairs FROM measurements m
            LEFT JOIN measurement_details d ON d.public_key=m.public_key AND d.at=m.at
            WHERE m.public_key=? AND m.at<=? ORDER BY m.at DESC LIMIT 1''',(key,now)).fetchone()
    latest=dict(latest) if latest else {}
    total,two=latest.get('neighbors'),latest.get('two_way')
    percent=100*two/total if total and two is not None and two<=total else None
    cards={'at':latest.get('at'),'period_seconds':store.DAY,'relay_24h':latest.get('relay_24h'),
           'neighbors':total,'two_way':two,'two_way_percent':percent,'pairs':latest.get('pairs'),'sole_pairs':latest.get('sole_pairs')}
    overall='Insufficient Data' if any(a['status']=='Insufficient Data' for a in assessment.values()) else 'Comparable observed measurements available'
    interpretation='Insufficient Data for a combined assessment. Available measured changes are shown separately below.'
    if overall!='Insufficient Data':
        relative=assessment['relative']['changes']
        delta=relative['copies']['percent']-relative['network']['percent']
        structure=[assessment[d]['changes'][f]['difference'] for d,f in (('connectivity','two_way'),('routing','pairs'),('routing','sole_pairs'))]
        if delta>.01 and all(v>=0 for v in structure):
            interpretation='Observed involvement increased relative to recorded mesh traffic, with stable or higher connectivity and routing indicators. This suggests greater observed contribution, not proven better delivery.'
        elif abs(delta)<=.01:
            interpretation='Repeater involvement changed at the same rate as observed mesh traffic. Increased activity alone does not establish a repeater-specific improvement; consider the connectivity and routing observations below.'
        else:
            interpretation='The indicators show mixed changes or lower relative involvement. The observations do not establish a consistent performance improvement or decline.'
    return {'start':start,'end':end,'now':now,'split':split,'step':step,'cards':cards,
            'forwarding':forwarding,'companion':companion,'snapshots':snapshots,'assessment':assessment,
            'overall':overall,'interpretation':interpretation,'caution':'Increased activity is not proof of improved performance. Observer coverage, traffic and routing may change. Relationships are inferred. Correlation does not prove causation.'}
