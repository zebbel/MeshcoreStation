"""Fast local-dashboard job creation/status; HTTP never waits on radio responses."""
import json
import sqlite3
from flask import request
from meshcorestation import config
from meshcorestation.bridge import bridge
from meshcorestation.storage import neighbor_snr_manual as manual
from meshcorestation.web.http import control_request_error,json_response


def worker_ready():
    runtime=bridge.runtime;worker=getattr(runtime,'neighbor_monitor',None)
    ready=bool(worker and worker.ready and worker.task and not worker.task.done() and worker.connected(runtime.companion)
        and bridge.loop and not bridge.loop.is_closed())
    return worker,ready


def register_manual_snr_routes(server):
    @server.route('/api/repeater-statistics/read-now',methods=['GET','POST'])
    def manual_snr():
        if control_request_error():return json_response(dict(ok=False,error='Open Read now from the local dashboard.'),403)
        try:
            worker,ready=worker_ready()
            if request.method=='GET':
                result=manual.snapshot(config.DB_PATH,request.args.get('public_key'))
                return json_response(dict(ok=True,ready=ready,**result))
            if request.mimetype!='application/json' or (request.content_length or 0)>2048:raise ValueError('Expected a managed repeater key.')
            raw=request.get_data(cache=True)
            if len(raw)>2048:raise ValueError('Read request is too large.')
            data=json.loads(raw)
            if not isinstance(data,dict) or set(data)!={'public_key'}:raise ValueError('Expected only a managed repeater public key.')
            if not ready:return json_response(dict(ok=False,error='Companion disconnected or neighbor collector offline. No read was queued.'),503)
            try:job=manual.enqueue(config.DB_PATH,data['public_key'])
            except manual.Busy as exc:
                return json_response(dict(ok=False,error=str(exc),ready=ready,**manual.snapshot(config.DB_PATH,data['public_key'])),409)
            try:bridge.loop.call_soon_threadsafe(worker.wakeup.set)
            except RuntimeError:
                manual.cancel_pending(config.DB_PATH,'Collector stopped before the read began; request a new read explicitly.')
                return json_response(dict(ok=False,error='Collector stopped; no automatic replay will be attempted.'),503)
            return json_response(dict(ok=True,ready=True,job=job,busy=True),202)
        except (ValueError,TypeError) as exc:return json_response(dict(ok=False,error=str(exc)),400)
        except (OSError,sqlite3.Error):return json_response(dict(ok=False,error='Manual read status storage unavailable. Existing observations are preserved.'),503)
