"""Firmware controls share the dashboard's local-origin protection."""
from urllib.parse import urlsplit
from flask import jsonify, request
from meshcorestation.bridge import bridge
from meshcorestation.web.companion_settings import allowed_host


def register_firmware_routes(server):
    @server.route('/api/companion/firmware', methods=['GET', 'POST'])
    def firmware():
        origin = request.headers.get('Origin')
        if (not allowed_host((urlsplit(request.host_url).hostname or '').lower())
                or request.headers.get('X-Meshcore-Control') != '1'
                or request.headers.get('Sec-Fetch-Site') == 'cross-site'
                or (origin and origin != request.host_url.rstrip('/'))):
            return jsonify(ok=False, error='Open firmware settings from this dashboard.'), 403
        try:
            body = request.get_json(silent=True) if request.method == 'POST' else {'action': 'status'}
            if not isinstance(body, dict) or len(str(body)) > 2048:
                raise ValueError('Invalid firmware request')
            result = bridge.request({**body, 'operation': 'firmware'})
            response = jsonify(result)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except Exception as exc:
            return jsonify(ok=False, error=str(exc)), 409
