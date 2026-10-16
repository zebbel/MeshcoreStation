"""Firmware controls share the dashboard's local-origin protection."""
import logging
from flask import jsonify, request
from meshcorestation.bridge import bridge
from meshcorestation.web.http import control_request_error, json_response as reply


def register_firmware_routes(server):
    @server.route('/api/companion/firmware', methods=['GET', 'POST'])
    def firmware():
        if control_request_error():
            return jsonify(ok=False, error='Open firmware settings from this dashboard.'), 403
        try:
            body = request.get_json(silent=True) if request.method == 'POST' else {'action': 'status'}
            if not isinstance(body, dict) or len(str(body)) > 2048:
                raise ValueError('Invalid firmware request')
            action = body.get('action', 'status')
            runtime = bridge.runtime
            if runtime is None:
                raise OSError('Radio runtime is starting; retry shortly.')
            if action == 'status':
                result = runtime.firmware.snapshot()
            elif action == 'check':
                logging.info('Checking companion firmware releases on GitHub')
                result = runtime.firmware.check_releases(body.get('source'))
                logging.info('Companion firmware check complete: %s compatible releases', len(result['releases']))
            elif action == 'install':
                result = bridge.request({**body, 'operation': 'firmware'}, timeout=10)
            else:
                raise ValueError('Unknown firmware operation')
            response = jsonify(result)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except Exception as exc:
            logging.warning('Companion firmware request failed: %s', exc)
            return jsonify(ok=False, error=str(exc)), 409
