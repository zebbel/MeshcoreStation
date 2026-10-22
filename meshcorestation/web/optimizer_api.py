"""Local Repeater Optimizer API. Reads are passive; only management sends radio."""
import json
import sqlite3
from pathlib import Path
from flask import request, Response
from meshcorestation.bridge import bridge
from meshcorestation.storage import passive_stats, optimizer_store, advisor_history
from meshcorestation.optimizer_engine import analyze, compare_history
from meshcorestation.web.http import control_request_error, json_response

def _authorized(key, token):
    if not isinstance(token,str) or len(token)>100:
        return False
    try:
        data=bridge.request({'operation':'optimizer_authorize',
                             'public_key':key,'session':token},timeout=5)
        return data.get('ok') is True
    except (OSError,TypeError,ValueError):
        return False


def register_optimizer_routes(server):
    @server.route('/repeater-optimizer')
    def page():
        html=Path(__file__).with_name('repeater_optimizer.html').read_text(encoding='utf-8')
        return Response(html,mimetype='text/html',
                        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @server.route('/api/repeater-optimizer/settings', methods=['GET','POST'])
    def settings_api():
        if control_request_error():
            return json_response({'ok':False,'error':'Open from the local dashboard.'},403)
        try:
            if request.method == 'POST':
                if request.mimetype != 'application/json':
                    raise ValueError('JSON required.')
                raw = request.stream.read(4097)
                if len(raw) > 4096:
                    raise ValueError('Request too large.')
                data = json.loads(raw)
                if not isinstance(data,dict):
                    raise ValueError('Expected object.')
                action = data.get('action')
                if action == 'clear' or (action == 'enabled' and data.get('enabled') is False):
                    if data.get('confirm') is not True:
                        raise ValueError('Confirm deleting optimizer data for all repeaters.')
                if action == 'clear':
                    state = optimizer_store.reset()
                elif action == 'enabled':
                    state = optimizer_store.set_enabled(data.get('enabled'))
                else:
                    raise ValueError('Unknown action.')
            else:
                state = optimizer_store.status()
            return json_response({'ok':True, **state})
        except (ValueError,TypeError) as exc:
            return json_response({'ok':False,'error':str(exc)},400)
        except (OSError,sqlite3.Error):
            return json_response({'ok':False,'error':'Optimizer storage is unavailable. Retry after checking storage.'},503)

    @server.route('/api/repeater-optimizer',methods=['GET','POST'])
    def api():
        if control_request_error():
            return json_response({'ok':False,'error':'Open from the local dashboard.'},403)
        try:
            state=optimizer_store.status()
            if not state['enabled']:
                return json_response({'ok':request.method=='GET','enabled':False,
                                      'error':'Repeater Optimizer is disabled. Enable it in Settings.'},
                                     200 if request.method=='GET' else 409)
            if request.method=='POST':
                if request.mimetype!='application/json':
                    raise ValueError('JSON required.')
                raw=request.stream.read(4097)
                if len(raw)>4096:
                    raise ValueError('Request too large.')
                data=json.loads(raw)
                if not isinstance(data,dict):
                    raise ValueError('Expected object.')
                key=optimizer_store.valid_key(data.get('public_key'))
                action=data.get('action')
                if action in ('profile','storage','clear_history'):
                    if not _authorized(key,data.get('session')):
                        return json_response({'ok':False,'error':'An active repeater administrator session is required.'},403)
                    optimizer_store.initialize()
                    if action=='profile':
                        saved=optimizer_store.update_profile(key,data.get('role'),data.get('polling'))
                        return json_response({'ok':True,'profile':saved})
                    if action=='clear_history':
                        if data.get('confirm') is not True:
                            raise ValueError('Confirm clearing the verified change history.')
                        removed=advisor_history.clear_verified_flood(key)
                        return json_response({'ok':True,'removed':removed})
                    settings=optimizer_store.update_config(data.get('settings'))
                    return json_response({'ok':True,'settings':settings})
                if action!='review':
                    raise ValueError('Unknown action.')
                current=data.get('current',{})
                if not isinstance(current,dict) or set(current)-{'flood.max','flood.max.unscoped'}:
                    raise ValueError('Invalid current settings.')
                if data.get('since',state['since'])!=state['since']:
                    current={}
                days=data.get('days',7)
            else:
                key=optimizer_store.valid_key(request.args.get('public_key'))
                days=int(request.args.get('days',7))
                current={}
            if type(days) is not int or days not in (1,7,14,30,60):
                raise ValueError('Choose 1, 7, 14, 30, 60 days.')
            stats=passive_stats.network_snapshot(key,days)
            profile=optimizer_store.profile(key)
            snapshots=optimizer_store.snapshots(key, limit=1)
            # Do not return every individual path to the browser.
            findings=analyze(stats,profile,snapshots,current)
            summary={k:v for k,v in stats.items() if k not in ('daily','scope')}
            summary['scope']={name:{key:value for key,value in record.items() if key!='hops'}
                              for name,record in stats['scope'].items()}
            history=advisor_history.recent(key)
            comparisons=compare_history(key,history)
            after=optimizer_store.status()
            if not after['enabled']:
                return json_response({'ok':True,'enabled':False})
            if after['since']!=state['since']:
                return json_response({'ok':False,'error':'Optimizer storage changed while loading. Retry loading fresh data.'},409)
            return json_response({'ok':True,'enabled':True,'since':state['since'],'profile':profile,'settings':optimizer_store.config(),
                                  'statistics':summary,'daily':stats['daily'][-365:],
                                  'neighbor_snapshots':snapshots,'analysis':findings,
                                  'history':history,'comparisons':comparisons})
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            return json_response({'ok':False,'error':str(exc)},400)
        except (OSError,sqlite3.Error):
            return json_response({'ok':False,'error':'Local statistics storage unavailable.'},503)
