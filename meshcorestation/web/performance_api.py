"""On-demand local performance reads and annotations; no radio/remote requests."""
import json
import time
import sqlite3
from flask import request
from meshcorestation.storage import performance_store as store, optimizer_store
from meshcorestation.web.http import control_request_error, json_response


def register_performance_routes(server):
    @server.route('/api/repeater-performance', methods=['GET','POST'])
    def performance():
        if control_request_error():
            return json_response({'ok':False,'error':'Open Repeater Performance from this dashboard.'},403)
        try:
            if request.method=='POST':
                if request.mimetype!='application/json':
                    raise ValueError('JSON required.')
                raw=request.stream.read(4097)
                if len(raw)>4096:
                    raise ValueError('Request too large.')
                data=json.loads(raw)
                if not isinstance(data,dict) or set(data)-{'public_key','action','description','at','id','revision'}:
                    raise ValueError('Invalid change-marker request.')
                key=optimizer_store.valid_key(data.get('public_key'))
                ident=store.marker_change(key,data.get('action'),data)
                return json_response({'ok':True,'public_key':key,'id':ident})
            if set(request.args)-{'public_key','days','marker_id','compare_days'}:
                raise ValueError('Unsupported performance parameter.')
            key=optimizer_store.valid_key(request.args.get('public_key'))
            days=int(request.args.get('days',7));compare_days=int(request.args.get('compare_days',7))
            if days not in (1,7,30) or compare_days not in (1,3,7):
                raise ValueError('Choose a supported observation window.')
            marker_id=int(request.args['marker_id']) if 'marker_id' in request.args else None
            if marker_id is not None and marker_id<=0:
                raise ValueError('Choose a valid change marker.')
            # Seed an already saved snapshot after an upgrade; never fetch remotely here.
            from meshcorestation.analyzer import service
            cached=service.cached(key)
            if cached and time.time()-store.RETENTION<=cached[0]<=time.time():
                store.record_analyzer(key,cached[0],cached[1])
            result=store.overview(key,days,marker_id=marker_id,compare_days=compare_days)
            from meshcorestation.web.repeater_names import known_repeaters
            return json_response({**result,'repeaters':known_repeaters()})
        except (ValueError,TypeError,OverflowError,KeyError) as exc:
            return json_response({'ok':False,'error':str(exc)},400)
        except (OSError,sqlite3.Error):
            return json_response({'ok':False,'error':'Performance history unavailable. Check local storage; no conclusion about network activity can be drawn.'},503)
