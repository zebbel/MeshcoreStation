"""Local settings/status only. HTTP requests never contact a repeater."""
import sqlite3
import json
from flask import request
from meshcorestation import config
from meshcorestation.bridge import bridge
from meshcorestation.storage import clock_sync
from meshcorestation.web.http import control_request_error, json_response


def register_clock_sync_routes(server):
    @server.route('/api/repeater-clock-sync', methods=['GET', 'POST'])
    def clock_sync_settings():
        if control_request_error():
            return json_response(dict(ok=False,error='Open clock synchronization settings from the local dashboard.'),403)
        try:
            if request.method == 'POST':
                if request.mimetype != 'application/json' or (request.content_length or 0)>2048:
                    raise ValueError('Expected clock settings (up to 2 KiB).')
                raw = request.stream.read(2049)
                if len(raw)>2048: raise ValueError('Clock settings are too large.')
                data = json.loads(raw)
                if not isinstance(data,dict): raise ValueError('Expected clock settings.')
                value = clock_sync.save(config.DB_PATH, data.get('public_key'), data.get('enabled'),
                    data.get('interval_hours'), data.get('revision'), data.get('acknowledge_uncertain',False))
            else:
                value = clock_sync.settings(config.DB_PATH,request.args.get('public_key'))
            worker = getattr(bridge.runtime,'clock_sync',None)
            running = bool(worker and worker.task and not worker.task.done())
            return json_response(dict(ok=True,config=value,running=running))
        except (ValueError,TypeError) as exc:
            return json_response(dict(ok=False,error=str(exc)),400)
        except (OSError,sqlite3.Error):
            return json_response(dict(ok=False,error='Clock synchronization storage unavailable. Existing settings are preserved.'),503)
