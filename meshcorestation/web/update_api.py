"""Update endpoints use the same local-origin guard as radio controls."""
from flask import jsonify, request
from meshcorestation import __version__, updater
from meshcorestation.web.http import control_request_error, json_response as reply


SUPPORTED_BRANCHES = {'V5': 'V5', 'V6': 'V6'}


def register_update_routes(server):
    try:
        revision = updater.local_revision()
    except Exception:
        revision = 'unknown'
    try:
        branch = updater.local_branch()
    except Exception:
        branch = 'unknown'

    @server.get('/api/update/health')
    def update_health():
        return jsonify(ok=True, revision=revision, version=__version__, branch=branch)

    @server.route('/api/update', methods=['GET', 'POST'])
    def updates():
        if control_request_error():
            return reply({'ok': False, 'error': 'Open Updates from this dashboard on your local network.'}, 403)
        try:
            if request.method == 'POST':
                body = request.get_json(silent=True) or {}
                if not isinstance(body, dict):
                    raise ValueError('Invalid update request.')
                if body.get('action') == 'branches':
                    return reply({'ok': True, 'branches': SUPPORTED_BRANCHES})
                selected = body.get('branch', branch)
                if body.get('action') in {'check', 'install'}:
                    if not isinstance(selected, str) or selected not in SUPPORTED_BRANCHES:
                        raise ValueError('Choose V5 or V6.')

                if body.get('action') == 'check':
                    return reply({'ok': True, 'check': updater.check(selected)})
                if body.get('action') == 'install':
                    updater.queue(body.get('target'), selected)
                else:
                    return reply({'ok': False, 'error': 'Unknown update action.'}, 400)
            return reply({'ok': True, 'version': __version__, 'revision': revision,
                          'check': updater.read('check.json'), 'status': updater.read('status.json'),
                          'ready': updater.ready(), 'branch': branch})
        except Exception as exc:
            return reply({'ok': False, 'error': str(exc)}, 409)
