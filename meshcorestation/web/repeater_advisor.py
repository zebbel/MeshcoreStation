"""Advisor settings, fresh evidence and review API. Radio writes use management."""
import json
import os
import re
import tempfile
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from flask import request, Response
from meshcorestation.config import DATA_DIR
from meshcorestation.storage import passive_stats, advisor_history
from meshcorestation.advisor_rules import DEFAULT, SOURCE, schema, validate, review
from meshcorestation.web.http import control_request_error, json_response

FILE = DATA_DIR / 'repeater-advisor.json'


def config():
    try:
        return validate(json.loads(FILE.read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError, KeyError):
        return json.loads(json.dumps(DEFAULT))


def save(settings):
    FILE.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=FILE.parent,delete=False) as stream:
            name=stream.name
            json.dump(settings,stream,indent=2)
        os.replace(name,FILE)
    finally:
        if name and os.path.exists(name): os.unlink(name)


def snapshot(days):
    """One consistent, indexed aggregation; no dashboard routes or neighbor lists."""
    from meshcorestation.bridge import bridge
    now=time.time();cutoff=now-days*86400
    try:
        with closing(passive_stats.connect()) as db:
            db.execute('BEGIN')
            selected=db.execute('SELECT * FROM selection WHERE id=1').fetchone()
            selection=dict(selected) if selected else {}
            health=dict(db.execute('SELECT * FROM health WHERE id=1').fetchone())
            row=db.execute("""SELECT COUNT(*) AS copies, COUNT(DISTINCT digest) AS unique_count,
                COUNT(digest)-COUNT(DISTINCT digest) AS repeated,
                COUNT(digest) AS identified, COUNT(DISTINCT route) AS routes,
                COUNT(DISTINCT CAST(at / 86400 AS INTEGER)) AS active_days,
                COALESCE(SUM(scoped=0),0) AS unscoped, MAX(json_array_length(route)) AS max_hops,
                MAX(CASE WHEN scoped=0 THEN json_array_length(route) END) AS max_unscoped_hops,
                COALESCE(SUM(kind=4),0) AS adverts
                FROM observations WHERE target=? AND at>=? AND at<=? AND ambiguous=0""",
                (selection.get('public_key',''),cutoff,now)).fetchone()
        collector=passive_stats.collector
        return {'days':days,'selection':selection,'copies':row['copies'],'unique':row['unique_count'],
                'evidence':dict(row),'usefulness':{'partial':selection.get('since',now)>cutoff or bool(health.get('trimmed_at') or health.get('dropped'))},
                'health':{**health,'running':bool(collector.thread and collector.thread.is_alive()),
                          'error':collector.error or health.get('error',''),'radio':bridge.status[0]}}
    except (sqlite3.Error,OSError,TypeError):
        return {'days':days,'health':{'error':'Statistics unavailable'}}


def register_advisor_routes(server):
    @server.route('/repeater-advisor')
    def advisor_page():
        html=Path(__file__).with_name('repeater_advisor.html').read_text(encoding='utf-8')
        return Response(html,mimetype='text/html',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @server.route('/api/repeater-advisor',methods=['GET','POST'])
    def advisor_api():
        if control_request_error():
            return json_response({'ok':False,'error':'Open advisor from this dashboard.'},403)
        try:
            settings=config()
            if request.method=='POST':
                if request.mimetype!='application/json': raise ValueError('Expected JSON.')
                raw=request.stream.read(16385)
                if len(raw)>16384: raise ValueError('Request too large.')
                body=json.loads(raw)
                if not isinstance(body,dict): raise ValueError('Expected object.')
                action=body.get('action')
                settings=validate(body.get('settings'))
                if action not in ('save','review'): raise ValueError('Unknown advisor action.')
                current=body.get('current',{})
                if not isinstance(current,dict) or len(current)>6: raise ValueError('Invalid current values.')
                key=body.get('public_key','')
            else:
                days=request.args.get('days')
                if days is not None:
                    settings={**settings,'min_days':int(days)}
                    validate(settings)
                key=request.args.get('public_key','')
                current={}
            if not isinstance(key,str) or (key and not re.fullmatch('[0-9a-f]{64}',key)): raise ValueError('Invalid repeater key.')
            if request.method=='POST' and action=='save': save(settings)
            data=snapshot(settings['min_days'])
            summary={k:data.get(k) for k in ('copies','unique','days','health','selection','evidence','usefulness')}
            return json_response({'ok':True,'settings':settings,'schema':schema(),'defaults':DEFAULT,'source':SOURCE,
                                  'statistics':summary,'review':review(current,settings,data,key),
                                  'history':advisor_history.recent(key) if key else []})
        except (ValueError,TypeError,KeyError) as exc:
            return json_response({'ok':False,'error':str(exc)},400)
        except (OSError, sqlite3.Error):
            return json_response({'ok':False,'error':'Advisor storage unavailable.'},503)
