"""Same-origin room management. Private identity seeds never leave the host."""
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from flask import jsonify, request, send_file
from meshcorestation.config import DATA_DIR
from meshcorestation.rooms.service import RoomService
from meshcorestation.web.companion_settings import allowed_host


def register_room_routes(server):
    @server.get('/rooms')
    def rooms_page():
        return send_file(Path(__file__).with_name('rooms.html'))

    @server.route('/api/rooms', methods=['GET', 'POST'])
    def rooms_api():
        def reply(body, status=200):
            response = jsonify(body)
            response.status_code = status
            response.headers['Cache-Control'] = 'no-store'
            return response
        origin = request.headers.get('Origin')
        if (not allowed_host((urlsplit(request.host_url).hostname or '').lower())
                or request.headers.get('X-Meshcore-Control') != '1'
                or request.headers.get('Sec-Fetch-Site') == 'cross-site'
                or (origin and origin != request.host_url.rstrip('/'))):
            return reply(dict(ok=False, error='Open room settings from this dashboard.'), 403)
        try:
            service = RoomService(DATA_DIR / 'rooms.db')
            from meshcorestation.bridge import bridge
            if request.method == 'POST':
                if request.mimetype != 'application/json':
                    return reply(dict(ok=False,error='Expected JSON.'),415)
                raw = request.stream.read(8193)
                if len(raw) > 8192:
                    raise ValueError('Request too large.')
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError('Invalid request.')
                action, rid = body.get('action'), body.get('room')
                if action not in ('create', 'restart'):
                    if type(rid) is not int or rid < 1:
                        raise ValueError('Select a room.')
                    service.details(rid)
                if action == 'qr':
                    from meshcorestation.web.companion_share import contact_card
                    return reply(contact_card(service.config(rid), contact_type=3))
                if action == 'create':
                    rid = service.create(body.get('name'))
                elif action == 'enabled':
                    service.set_enabled(rid, body.get('enabled'))
                elif action == 'scope':
                    service.configure_scope(rid, body.get('scope_key'))
                elif action == 'grant':
                    # Administration is dashboard-local, not remote CLI access.
                    if body.get('role') not in ('reader', 'writer'):
                        raise ValueError('Choose reader or writer.')
                    service.grant(rid, body.get('key'), body.get('role'))
                elif action == 'revoke':
                    service.revoke(rid, body.get('key'))
                elif action == 'post':
                    service.local_post(rid, body.get('text'))
                elif action == 'restart':
                    result = bridge.request({'operation':'room_restart'}, timeout=20)
                    if not result.get('ok'):
                        raise ValueError(result.get('error','Room restart failed.'))
                else:
                    raise ValueError('Unknown action.')
            worker = getattr(bridge.runtime, 'rooms', None)
            status = worker.status() if worker else dict(running=False,error='Room worker unavailable; connect the companion.',sessions=0,dropped_packets=0)
            rooms = []
            for row in service.rooms():
                detail = service.details(row['id'])
                detail['contact_uri'] = 'meshcore://contact/add?' + urlencode(dict(name=detail['name'],public_key=detail['public_key'],type=3))
                rooms.append(detail)
            return reply(dict(ok=True, rooms=rooms, status=status))
        except (ValueError, TypeError, KeyError, PermissionError) as exc:
            return reply(dict(ok=False,error=str(exc)),400)
        except (sqlite3.Error, OSError) as exc:
            return reply(dict(ok=False,error='Room service unavailable: '+str(exc)),503)
