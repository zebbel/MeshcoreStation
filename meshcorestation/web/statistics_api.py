"""Read-only recording health, independent of UI/telemetry collection controls."""
import sqlite3
from flask import jsonify, request
from meshcorestation import config
from meshcorestation.bridge import bridge
from meshcorestation.storage import passive_stats


def register_statistics_routes(server):
    @server.get('/api/repeater-statistics/status')
    def statistics_status():
        try:
            value = passive_stats.snapshot(config.DB_PATH, request.args.get('public_key') or None)
            runtime = bridge.runtime
            collector = getattr(runtime, 'statistics', None)
            value['health'] = collector.health(value['selected']) if collector else dict(
                running=False, connected=False, queued=0, dropped=0, invalid=0,
                error='Statistics collector is not running.', repeater_error='', last_write=None)
            return jsonify(value)
        except ValueError as exc:
            return jsonify(ok=False,error=str(exc)),400
        except (OSError,sqlite3.Error):
            return jsonify(ok=False,error='Recording status unavailable. Saved history has not been deleted.'),503

    @server.get('/api/repeater-statistics/view')
    def statistics_view():
        from meshcorestation.storage.statistics_view import QueryTimeout
        from meshcorestation.web.statistics_service import saved_view,StatisticsBusy,StatisticsWorkerError
        from meshcorestation.web.http import json_response
        try:
            raw=request.args.get('days','1')
            if raw not in {'1','7','30'}:raise ValueError('Choose 24 hours, 7 days or 30 days.')
            return json_response(saved_view(config.DB_PATH,request.args.get('public_key') or None,int(raw)))
        except ValueError as exc:return json_response(dict(ok=False,error=str(exc)),400)
        except QueryTimeout as exc:
            return json_response(dict(ok=False,error_code='QUERY_TIMEOUT',stage=exc.stage,diagnostics=exc.diagnostics,error='The server query budget was reached during '+exc.stage+'. Try a shorter period. Recording continues; saved data is preserved.'),504)
        except StatisticsWorkerError:
            return json_response(dict(ok=False,error_code='WORKER_ERROR',error='The isolated statistics worker is unavailable. Refresh the saved view; recording status remains available.'),503)
        except StatisticsBusy as exc:
            response=json_response(dict(ok=False,error_code='STATISTICS_BUSY',error=str(exc)),429)
            response.headers['Retry-After']='2';return response
        except sqlite3.Error as exc:
            busy=getattr(exc,'sqlite_errorcode',None) in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)
            return json_response(dict(ok=False,error_code='DATABASE_BUSY' if busy else 'DATABASE_ERROR',error='Saved statistics database is busy. Try again shortly; collection continues.' if busy else 'Saved statistics database could not be read. Check storage and application logs; existing history is preserved.'),503)
        except OSError:
            return json_response(dict(ok=False,error_code='STORAGE_ERROR',error='Statistics storage or scratch space is unavailable. Check free space; the collection reserve and existing history are preserved.'),503)

    @server.route('/api/repeater-statistics/regions',methods=['GET','POST'])
    def statistics_regions():
        from meshcorestation.storage.statistics_view import region_config,save_regions
        from meshcorestation.web.http import control_request_error,json_response
        if control_request_error():return json_response(dict(ok=False,error='Open region settings from the local dashboard.'),403)
        try:
            if request.method=='POST':
                if request.mimetype!='application/json' or (request.content_length or 0)>8192:raise ValueError('Expected a region list (up to 8 KiB).')
                raw=request.get_data(cache=True)
                if len(raw)>8192:raise ValueError('Region configuration is too large.')
                body=request.get_json(silent=True)
                if not isinstance(body,dict):raise ValueError('Expected region settings.')
                save_regions(config.DB_PATH,body.get('regions'))
            return json_response(dict(ok=True,regions=region_config(config.DB_PATH)))
        except (ValueError,TypeError):return json_response(dict(ok=False,error='Invalid region settings. Use up to 64 distinct names and optional 32-hex keys; Unknown and Unscoped are reserved.'),400)
        except (OSError,sqlite3.Error):return json_response(dict(ok=False,error='Region settings unavailable. Existing observations are preserved.'),503)
