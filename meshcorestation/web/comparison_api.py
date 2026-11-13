"""Local journal controls and bounded saved-only comparison requests."""
import sqlite3
from flask import request
from meshcorestation import config
from meshcorestation.storage import repeater_comparison as store
from meshcorestation.storage.statistics_view import QueryTimeout
from meshcorestation.web.http import control_request_error,json_response
from meshcorestation.web.statistics_service import comparison_view,StatisticsBusy,StatisticsWorkerError


def register_comparison_routes(server):
    @server.route('/api/repeater-comparison/changes',methods=['GET','POST'])
    def changes():
        if control_request_error():return json_response(dict(ok=False,error='Open change history from the local dashboard.'),403)
        try:
            if request.method=='GET':return json_response(store.journal(config.DB_PATH,request.args.get('public_key') or None,int(request.args.get('offset','0'))))
            if request.mimetype!='application/json' or (request.content_length or 0)>4096:raise ValueError('Expected change details up to 4 KiB.')
            data=request.get_json(silent=True)
            if not isinstance(data,dict) or set(data)-{'public_key','action','description','id','confirm'}:raise ValueError('Use a description and selected repeater; timestamps are assigned by the server.')
            return json_response(store.mutate(config.DB_PATH,data.get('public_key'),data.get('action'),data.get('description'),data.get('id'),data.get('confirm')))
        except (ValueError,TypeError) as exc:return json_response(dict(ok=False,error=str(exc)),400)
        except (OSError,sqlite3.Error):return json_response(dict(ok=False,error='Change history storage unavailable; existing records are preserved.'),503)

    @server.get('/api/repeater-comparison/view')
    def comparison():
        if control_request_error():return json_response(dict(ok=False,error='Open comparison from the local dashboard.'),403)
        try:
            key=request.args.get('public_key');change_id=int(request.args.get('change_id','0'));days=int(request.args.get('days','1'))
            if change_id<=0 or days not in (1,7,30):raise ValueError('Select a saved change and comparison period.')
            return json_response(comparison_view(config.DB_PATH,key,change_id,days))
        except (ValueError,TypeError) as exc:return json_response(dict(ok=False,error=str(exc)),400)
        except QueryTimeout as exc:
            resume = bool(exc.diagnostics.get('classification_progress_saved'))
            hint = 'Run the comparison again to resume saved progress.' if resume else 'Try again or select a shorter comparison period.'
            return json_response(dict(ok=False,error_code='QUERY_TIMEOUT',stage=exc.stage,resume=resume,
                error=f'Comparison exceeded the shared query budget during {exc.stage}. {hint}'),504)
        except StatisticsBusy as exc:return json_response(dict(ok=False,error_code='STATISTICS_BUSY',error=str(exc)),429)
        except (StatisticsWorkerError,OSError,sqlite3.Error):return json_response(dict(ok=False,error='Saved comparison unavailable. Collection and stored history are preserved.'),503)
