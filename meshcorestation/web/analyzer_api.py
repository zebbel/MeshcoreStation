"""Local, on-demand API. A failure is never represented as zero traffic."""
import sqlite3
from flask import request
from meshcorestation.analyzer import service
from meshcorestation.web.http import control_request_error, json_response


def register_analyzer_routes(server):
    @server.get('/api/repeater-network')
    def network():
        if control_request_error():
            return json_response({'ok':False,'error':'Open monitoring from this dashboard.'},403)
        try:
            if set(request.args) - {'public_key','refresh','cache_only'}:
                raise ValueError('Unsupported monitoring parameter.')
            for flag in ('refresh','cache_only'):
                if request.args.get(flag,'0') not in ('0','1'): raise ValueError('Invalid monitoring option.')
            result=service.snapshot(request.args.get('public_key'),
                force=request.args.get('refresh')=='1', cache_only=request.args.get('cache_only')=='1')
            from meshcorestation.web.repeater_names import known_repeaters
            return json_response({**result,'repeaters':known_repeaters()})
        except ValueError as exc:
            return json_response({'ok':False,'error':str(exc)},400)
        except (OSError,sqlite3.Error):
            return json_response({'ok':False,'error':'Local monitoring cache unavailable. Check storage.'},503)
