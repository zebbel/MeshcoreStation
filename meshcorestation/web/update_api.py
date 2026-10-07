"""Update endpoints use the same local-origin guard as radio controls."""
from urllib.parse import urlsplit
from flask import jsonify, request
from meshcorestation import __version__, updater
from meshcorestation.web.companion_settings import allowed_host


def register_update_routes(server):
    try:
        revision = updater.local_revision()
    except Exception:
        revision = 'unknown'

    @server.get('/api/update/health')
    def update_health():
        return jsonify(ok=True, revision=revision, version=__version__)

    @server.route('/api/update', methods=['GET', 'POST'])
    def updates():
        def reply(body, code=200):
            response = jsonify(body)
            response.status_code = code
            response.headers['Cache-Control'] = 'no-store'
            return response
        origin = request.headers.get('Origin')
        if (not allowed_host((urlsplit(request.host_url).hostname or '').lower())
                or request.headers.get('X-Meshcore-Control') != '1'
                or request.headers.get('Sec-Fetch-Site') == 'cross-site'
                or (origin and origin != request.host_url.rstrip('/'))):
            return reply({'ok': False, 'error': 'Open Updates from this dashboard on your local network.'}, 403)
        try:
            if request.method == 'POST':
                body = request.get_json(silent=True) or {}
                if body.get('action') == 'check':
                    return reply({'ok': True, 'check': updater.check()})
                if body.get('action') == 'install':
                    updater.queue(body.get('target'))
                else:
                    return reply({'ok': False, 'error': 'Unknown update action.'}, 400)
            return reply({'ok': True, 'version': __version__, 'revision': revision,
                          'check': updater.read('check.json'), 'status': updater.read('status.json'),
                          'ready': updater.ready()})
        except Exception as exc:
            return reply({'ok': False, 'error': str(exc)}, 409)
