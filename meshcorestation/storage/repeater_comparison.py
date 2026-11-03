"""Persistent change journal and bounded, saved-only before/after analysis."""
from contextlib import closing,nullcontext
from pathlib import Path
import re
import sqlite3
from statistics import median
import time
from meshcorestation.storage.connection import connect
from meshcorestation.storage import passive_stats
from meshcorestation.storage.neighbor_snr import managed
from meshcorestation.storage.voltage_store import MEMBERSHIP_LOCK

SCHEMA='''CREATE TABLE IF NOT EXISTS repeater_changes(
 id INTEGER PRIMARY KEY,public_key TEXT NOT NULL,recorded_at REAL NOT NULL,description TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS repeater_changes_time ON repeater_changes(public_key,recorded_at,id);'''


def description(value):
    if not isinstance(value,str) or not value.strip() or len(value.strip())>500 or re.search('[\\x00-\\x1f\\x7f]',value):
        raise ValueError('Enter a change description of 1–500 characters without control characters.')
    return value.strip()


def journal(path,key=None,offset=0):
    if type(offset) is not int or not 0<=offset<=1000000:raise ValueError('Invalid journal offset.')
    state=passive_stats.snapshot(path,key);key=state['selected']
    with closing(connect(Path(path).as_uri()+'?mode=ro',timeout=.25)) as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM repeater_changes WHERE public_key=? ORDER BY recorded_at,id LIMIT 201 OFFSET ?',(key,offset))]
    return dict(ok=True,selected=key,repeaters=state['repeaters'],changes=rows[:200],has_more=len(rows)>200,offset=offset)


def mutate(path,key,action,text=None,change_id=None,confirm=False):
    with MEMBERSHIP_LOCK,closing(connect(path,timeout=.25)) as db,db:
        managed(db,key)
        if action=='create':
            value=description(text);stamp=time.time()
            change_id=db.execute('INSERT INTO repeater_changes(public_key,recorded_at,description) VALUES(?,?,?)',(key,stamp,value)).lastrowid
        elif action in ('edit','delete'):
            if type(change_id) is not int or not db.execute('SELECT 1 FROM repeater_changes WHERE id=? AND public_key=?',(change_id,key)).fetchone():raise ValueError('Select an existing change for this repeater.')
            if action=='edit':db.execute('UPDATE repeater_changes SET description=? WHERE id=? AND public_key=?',(description(text),change_id,key))
            else:
                if confirm is not True:raise ValueError('Confirm deletion of the change record.')
                db.execute('DELETE FROM repeater_changes WHERE id=? AND public_key=?',(change_id,key))
        else:raise ValueError('Unknown journal operation.')
        row=db.execute('SELECT * FROM repeater_changes WHERE id=? AND public_key=?',(change_id,key)).fetchone()
        return dict(ok=True,change=dict(row) if row else None)


def _period(view):
    totals=view['totals'];coverage=view['coverage_seconds'];neighbors=view['neighbors']
    count=totals.get('receptions',0)
    available=bool(count or coverage)
    complete=bool(view['coverage_known'] and coverage>=view['coverage_expected']-1e-6)
    return dict(start=view['start'],end=view['end'],future=view.get('future',False),complete=complete,
        coverage_known=view['coverage_known'],recorded_seconds=coverage,expected_seconds=view['coverage_expected'],
        receptions=count if available else None,unique_packets=totals.get('unique_packets',0) if available else None,
        repeated=totals.get('repeated',0) if available else None,unidentified=totals.get('unidentified',0) if available else None,
        traffic_per_recorded_hour=(view['covered_receptions']/(coverage/3600) if coverage and view.get('covered_receptions') is not None else None),
        covered_receptions=view.get('covered_receptions'),neighbors=len(neighbors) if available else None,
        one_way=sum(bool(r['incoming'])!=bool(r['outgoing']) for r in neighbors) if available else None,
        two_way=sum(bool(r['incoming'] and r['outgoing']) for r in neighbors) if available else None,
        snr_samples=sum(r['samples'] for r in view['neighbor_snr'] if r['resolution']=='matched'),
        uncertain_snr_groups=sum(r['resolution']!='matched' for r in view['neighbor_snr']),notes=view['notes'])


def aggregate(path,key,change_id,days,now=None):
    from meshcorestation.storage.statistics_view import aggregate as view,QUERY_BUDGET_SECONDS,QueryTimeout
    if days not in (1,7,30) or type(change_id) is not int:raise ValueError('Select a change and a 24-hour, 7-day or 30-day period.')
    deadline=time.monotonic()+QUERY_BUDGET_SECONDS;clock=time.time() if now is None else now
    with closing(connect(Path(path).as_uri()+'?mode=ro',timeout=.25)) as main:
        main.execute('BEGIN');managed(main,key)
        row=main.execute('SELECT * FROM repeater_changes WHERE id=? AND public_key=?',(change_id,key)).fetchone()
        if not row:raise ValueError('Selected change is unavailable for this repeater.')
        change=dict(row);t=change['recorded_at'];duration=days*86400
        registry={r['public_key']:dict(r) for r in main.execute('SELECT public_key,name,latitude,longitude FROM repeaters')}
        regions=[dict(r) for r in main.execute('SELECT name,scope_key FROM statistics_regions UNION SELECT name,scope_key FROM scopes')]
        overlapping=[dict(r) for r in main.execute('SELECT id,description,recorded_at FROM repeater_changes WHERE public_key=? AND id!=? AND recorded_at>=? AND recorded_at<? ORDER BY recorded_at,id LIMIT 201',(key,change_id,t-duration,t+duration))]
    source_path=passive_stats.statistics_path(path,key)
    with (closing(sqlite3.connect(source_path.as_uri()+'?mode=ro',uri=True,timeout=.25)) if source_path.exists() else nullcontext(None)) as source:
        if source:
            source.execute('PRAGMA query_only=ON');source.execute('BEGIN')
            source.execute('SELECT 1 FROM observations LIMIT 1').fetchone() # one immutable history snapshot for both windows
        values=[]
        for start,end in ((t-duration,t),(t,t+duration)):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise QueryTimeout('comparison')
            values.append(view(path,key,days,now=clock,start=start,end=end,_source=source,_metadata=(registry,regions),_budget=remaining,_covered=True))
    before,after=values
    b={r['public_key']:r for r in before['neighbor_snr'] if r['resolution']=='matched'}
    a={r['public_key']:r for r in after['neighbor_snr'] if r['resolution']=='matched'}
    matched=[]
    for identity in sorted(b.keys()&a.keys()):
        left,right=b[identity],a[identity]
        matched.append(dict(public_key=identity,name=right['name'] or left['name'],before=left['average_snr'],after=right['average_snr'],
                            difference_db=right['average_snr']-left['average_snr'],before_samples=left['samples'],after_samples=right['samples']))
    warnings=[]
    if after.get('future'):warnings.append('The after-period extends into the future; this comparison is incomplete.')
    periods=[_period(v) for v in values]
    if not all(p['complete'] for p in periods):warnings.append('Passive recording coverage is incomplete or unknown. Observed counts are lower bounds, not final period totals.')
    if not matched or any(min(r['before_samples'],r['after_samples'])<2 for r in matched):warnings.append('Insufficient matched-neighbor SNR history for a reliable trend; single samples remain visible.')
    if any('limited' in note.lower() for value in values for note in value['notes']):warnings.append('Neighbor summaries are output-limited; neighbor differences are partial.')
    if overlapping:warnings.append('Other logged changes overlap these windows and may affect interpretation.')
    warnings.append('SNR sampling coverage is not equivalent to passive collection uptime; sample counts are shown separately.')
    warnings.append('Changes can coincide with different network traffic or radio conditions. Correlation does not establish causation or packet-delivery success.')
    return dict(ok=True,generated_at=clock,selected=key,days=days,change=change,before=periods[0],after=periods[1],matched=matched,
        median_snr_change=median(r['difference_db'] for r in matched) if matched else None,
        newly_heard=[a[k] for k in sorted(a.keys()-b.keys())],not_heard_after=[b[k] for k in sorted(b.keys()-a.keys())],
        new_observed_neighbors=[r for r in after['neighbors'] if r['public_key'] not in {n['public_key'] for n in before['neighbors']}],
        not_observed_after=[r for r in before['neighbors'] if r['public_key'] not in {n['public_key'] for n in after['neighbors']}],
        overlapping_changes=overlapping[:200],overlap_limit=len(overlapping)>200,warnings=warnings,
        interpretation='Insufficient Data' if not matched else 'Preliminary observed differences; increased activity alone is not evidence of improved radio performance.')
