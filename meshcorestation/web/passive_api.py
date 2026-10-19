"""Local dashboard controls for passive statistics; never dispatches radio requests."""
from flask import request
from meshcorestation.web.http import control_request_error, json_response as reply
from meshcorestation.storage import passive_stats as stats


def register_passive_routes(server):
    @server.route('/api/repeater-statistics',methods=['GET','POST'])
    def passive_statistics():
        if control_request_error():
            return reply({'ok':False,'error':'Open statistics from this dashboard.'},403)
        try:
            days=int(request.args.get('days','1'))
            if days not in (1,7,30): raise ValueError('Choose 24 hours, 7 days or 30 days.')
            if request.method=='POST':
                body=request.get_json(silent=True)
                if not isinstance(body,dict) or not isinstance(body.get('public_key'),str):
                    raise ValueError('Select a repeater.')
                if 'enabled' in body:
                    stats.track(body['public_key'].lower(), body['enabled'])
                else:
                    stats.select(body['public_key'].lower())
            return reply({'ok':True,**stats.snapshot(days, request.args.get('public_key'))})
        except ValueError as exc:
            return reply({'ok':False,'error':str(exc)},400)
        except Exception:
            return reply({'ok':False,'error':'Statistics unavailable. Check service logs and restart after updating.'},503)
