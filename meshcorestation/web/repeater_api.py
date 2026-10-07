"""Bounded HTTP input for remote repeater requests; common origin guards apply."""
import json
import re
from meshcorestation.bridge import bridge

ACTIONS = {'login', 'logout', 'status', 'telemetry', 'neighbors', 'acl', 'read', 'write', 'action', 'regions_read', 'region', 'permission'}


def repeater_request(request):
    if request.method != 'POST' or request.mimetype != 'application/json':
        return {'ok': False, 'error': 'Expected a JSON POST.'}, 415
    try:
        raw = request.stream.read(8193)
        if len(raw) > 8192:
            raise ValueError()
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get('action') not in ACTIONS:
            raise ValueError()
        if not isinstance(payload.get('public_key'), str) or not re.fullmatch('[0-9a-f]{64}', payload['public_key']):
            raise ValueError()
        if payload['action'] != 'login' and (not isinstance(payload.get('session'), str) or len(payload['session']) > 100):
            raise ValueError()
        if 'offset' in payload and (type(payload['offset']) is not int or not 0 <= payload['offset'] <= 65535):
            raise ValueError()
        json.dumps(payload, allow_nan=False)
    except (ValueError, TypeError):
        return {'ok': False, 'error': 'Invalid repeater request.'}, 400
    try:
        result = bridge.request({**payload, 'operation': 'repeater'})
        return result, 200 if result.get('ok') else 409
    except (OSError, ValueError, TypeError):
        return {'ok': False, 'error': 'Repeater request could not be confirmed. A submitted change may have applied. Read before retrying.'}, 503
