"""Local dashboard controls for passive statistics; never dispatches radio requests."""
from urllib.parse import urlsplit
from flask import jsonify, request
from meshcorestation.web.companion_settings import allowed_host
from meshcorestation.storage import passive_stats as stats


def register_passive_routes(server):
    @server.route('/api/repeater-statistics',methods=['GET','POST'])
    def passive_statistics():
        def reply(body, code=200):
            response=jsonify(body);response.status_code=code
            response.headers['Cache-Control']='no-store'
            return response
        origin=request.headers.get('Origin')
        if (not allowed_host((urlsplit(request.host_url).hostname or '').lower())
                or request.headers.get('X-Meshcore-Control')!='1'
                or request.headers.get('Sec-Fetch-Site')=='cross-site'
                or (origin and origin!=request.host_url.rstrip('/'))):
            return reply({'ok':False,'error':'Open statistics from this dashboard.'},403)
        try:
            days=int(request.args.get('days','1'))
            if days not in (1,7,30): raise ValueError('Choose 24 hours, 7 days or 30 days.')
            if request.method=='POST':
                body=request.get_json(silent=True)
                if not isinstance(body,dict) or not isinstance(body.get('public_key'),str):
                    raise ValueError('Select a repeater.')
                stats.select(body['public_key'].lower())
            return reply({'ok':True,**stats.snapshot(days)})
        except ValueError as exc:
            return reply({'ok':False,'error':str(exc)},400)
        except Exception:
            return reply({'ok':False,'error':'Statistics unavailable. Check service logs and restart after updating.'},503)
