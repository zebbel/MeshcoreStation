"""Germany-aware, explainable repeater hop-limit trial candidates.

The companion observes only received paths. A sample percentile is NOT a
proven delivery requirement; never represent a suggested cap as guaranteed.
"""
import math

MARGINS = {'local': 2, 'hybrid': 3, 'regional': 4, 'unknown': 4}


def analyze(stats, profile, snapshots, current):
    role=profile['role']
    last=snapshots[0] if snapshots else None
    gaps=[]
    if role=='unknown':
        gaps.append('Choose a repeater role to evaluate network reachability requirements.')
    if stats['copies']<100 or stats['matching_copies']<30:
        gaps.append('Insufficient observations (at least 100 total and 30 matching packets).')
    if stats['active_days']<3:
        gaps.append('Less than three active days.')
    if stats['matching_copies'] and stats['ambiguous']>stats['matching_copies']/5:
        gaps.append('Too many ambiguous short path hashes.')
    if stats['partial']:
        gaps.append('Observation window is incomplete or previously truncated.')
    if stats['collector_error']:
        gaps.append('The passive collector reports missing data.')
    if not last or last['at']<stats['now']-14*86400:
        gaps.append('Recent neighbor snapshot missing (not older than 14 days).')
    elif not last['complete']:
        gaps.append('Latest neighbor list is partial; other neighbors may be missing.')
    results=[]
    for field,label in [('flood.max','scoped'),('flood.max.unscoped','unscoped')]:
        data=stats['scope'][label]
        reasons=list(gaps)
        if data['target']<15 or data['count']<30:
            reasons.append('Not enough observed paths in this scope involving the selected repeater.')
        histogram={int(k):v for k,v in data['hist'].items()}
        if not histogram:
            reasons.append('No hop-count distribution is available.')
        try:
            old=int(current.get(field))
            if not 0<=old<=64:
                raise ValueError()
        except (ValueError,TypeError):
            old=None
            reasons.append('Read the current setting with the manual LoRa button.')
        count=sum(histogram.values())
        target_p90=math.ceil(.90*count)
        running=0;p90=None
        for hops,quantity in sorted(histogram.items()):
            running+=quantity
            if p90 is None and running>=target_p90:
                p90=hops
        margin=MARGINS[role]
        suggested=None
        if not reasons:
            trial=min(64,max(p90+margin,max(histogram),3 if label=='unscoped' else 5))
            if old is not None and trial<old:
                suggested=trial
            else:
                reasons.append('Measured traffic does not justify lowering the current limit.')
        results.append({'field':field,'current':old,'suggested':suggested,
                        'can_apply':suggested is not None,
                        'confidence':'experimental' if suggested is not None else 'insufficient',
                        'observed':data['count'],'matching':data['target'],
                        'p90':p90,'max':max(histogram) if histogram else None,
                        'reasons':reasons,
                        'explanation':(
                            f'Conservative trial heuristic: observed route p90 ({p90}) + '
                            f'{margin} role-dependent margin. Not a verified optimum; '
                            'unobserved destinations might require more hops. Check '
                            'reachability and compare traffic before and after.'
                            if suggested is not None else
                            'Observed path lengths alone cannot establish a safe hop limit.')})
    return {'recommendations':results,'data_gaps':gaps,'role':role,
            'notes':['German communities use region scopes and often constrain unscoped flooding. Values are local, not universal.',
                     'Only packets received by the MeshcoreStation companion were measured.',
                     'A neighbor record proves recent advertisement reception, not bidirectional delivery.']}


def compare_history(key, changes, now=None):
    """Two 24-hour passive-only observations around verified flood limit writes."""
    from meshcorestation.storage import passive_stats
    from contextlib import closing
    import time
    now=time.time() if now is None else now
    results={}
    verified=[r for r in changes if r.get('status')=='verified'
              and r.get('actual')==r.get('requested')
              and r.get('field') in ('flood.max','flood.max.unscoped')]
    with closing(passive_stats.connect()) as db:
        db.execute('BEGIN')
        earliest=db.execute('SELECT MIN(at) FROM network_observations').fetchone()[0]
        for change in verified[:10]:
            at=change['at']; first=at-86400; second=at+3600; end=second+86400
            item={'status':'unavailable','message':'Comparison unavailable.'}
            results[str(change['id'])]=item
            if earliest is None or earliest>first:
                item['message']='Full 24h passive baseline is missing.'
                continue
            if now<end:
                item.update(status='collecting',next_at=end,
                            message='Collecting the 24h after-window.')
                continue
            if first<now-60*86400:
                item['message']='Baseline is beyond detailed retention.'
                continue
            patterns=['%|'+key[:n]+'|%' for n in (2,4,6)]
            where=' OR '.join("('|'||route||'|') LIKE ?" for _ in patterns)
            def sample(start,stop):
                row=db.execute(f"""SELECT COUNT(*) copies,COUNT(digest) identified,
                  COUNT(DISTINCT digest) unique_count,COALESCE(SUM(scoped=0),0) unscoped,
                  COALESCE(SUM(kind=4),0) adverts FROM network_observations
                  WHERE at>=? AND at<? AND ({where})""",(start,stop,*patterns)).fetchone()
                d=dict(row)
                for name,num,den in [('repeated_pct',d['identified']-d['unique_count'],d['identified']),
                                     ('unscoped_pct',d['unscoped'],d['copies']),
                                     ('advert_pct',d['adverts'],d['copies'])]:
                    d[name]=round(100*num/den,1) if den else None
                return d
            before,after=sample(first,at),sample(second,end)
            item.update(before=before,after=after)
            if min(before['copies'],after['copies'])<100 or min(before['identified'],after['identified'])<70:
                item.update(status='insufficient',message='Insufficient packets in one or both windows.')
                continue
            if (min(before['identified']/before['copies'],after['identified']/after['copies'])<.7 or
                min(before['identified'],after['identified'])/max(before['identified'],after['identified'])<.5):
                item.update(status='incomparable',message='Traffic volume or completeness differs too much.')
                continue
            others=sum(1 for x in changes if x['id']!=change['id'] and
                       isinstance(x.get('at'),(int,float)) and first<=x['at']<=end)
            item.update(status='descriptive',message='Paired observations are available.',
                        delta={name:round(after[name]-before[name],1) for name in
                               ('repeated_pct','unscoped_pct','advert_pct')},
                        notes=['Only companion-received traffic is measured; no causal or delivery guarantee.',
                               'Traffic mix and external changes may differ.'])
            if others:
                item['notes'].append(f'{others} other advisor changes overlap.')
    return results
