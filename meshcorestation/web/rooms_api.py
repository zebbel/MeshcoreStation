"""Same-origin room management. Private identity seeds never leave the host."""
import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode
from flask import request, Response
from meshcorestation.config import DATA_DIR, DB_PATH
from meshcorestation.rooms.service import RoomService
from meshcorestation.web.http import control_request_error, json_response as reply


def delete_room_with_battery_guard(service, rid, expected):
    """Check all managed battery destinations before removing a room.

    Lock the station DB first to serialize against concurrent battery-setting
    saves, which also take the station write lock before reading room settings.
    The station database may not exist on a room-only first installation.
    """
    if not DB_PATH.exists():
        service.delete(rid, expected['name'], expected['public_key'])
        return
    with closing(sqlite3.connect(DB_PATH.as_uri() + '?mode=rw', uri=True, timeout=5)) as station:
        station.execute('BEGIN IMMEDIATE')
        table = station.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='voltage_config'"
        ).fetchone()
        if table:
            fields = {col[1] for col in station.execute('PRAGMA table_info(voltage_config)')}
            if 'report_target' in fields:
                condition = "report_target=?"
                if 'managed' in fields:
                    condition += ' AND managed=1'
                used = station.execute(
                    f'SELECT 1 FROM voltage_config WHERE {condition} LIMIT 1',
                    (f'room:{rid}',)
                ).fetchone()
                if used:
                    raise ValueError('This room is used as a repeater telemetry report destination. '
                                     'Change the destination in Repeater management before deleting it.')
        service.delete(rid, expected['name'], expected['public_key'])
        station.commit()


def register_room_routes(server):
    services = {}
    service_lock = threading.Lock()

    def room_service():
        # Service contains no shared SQLite connection. Each operation opens its own.
        path = DATA_DIR / 'rooms.db'
        with service_lock:
            if path not in services:
                services[path] = RoomService(path)
            return services[path]

    @server.get('/rooms')
    def rooms_page():
        return Response(Path(__file__).with_name('rooms.html').read_text(encoding='utf-8'),
                        mimetype='text/html',headers={'Cache-Control':'no-store'})

    @server.route('/api/rooms', methods=['GET', 'POST'])
    def rooms_api():
        if control_request_error():
            return reply(dict(ok=False, error='Open room settings from this dashboard.'), 403)
        try:
            service = room_service()
            from meshcorestation.bridge import bridge
            if request.method == 'POST':
                if request.mimetype != 'application/json':
                    return reply(dict(ok=False,error='Expected JSON.'),415)
                if request.content_length is not None and request.content_length > 8192:
                    raise ValueError('Request too large.')
                raw = request.get_data(cache=True)
                if len(raw) > 8192:
                    raise ValueError('Request too large.')
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError('Invalid request.')
                action, rid = body.get('action'), body.get('room')
                if action not in ('create', 'restart'):
                    if type(rid) is not int or rid < 1:
                        raise ValueError('Select a room.')
                    service.config(rid)
                if action == 'qr':
                    from meshcorestation.web.companion_share import contact_card
                    return reply(contact_card(service.config(rid), contact_type=3))
                if action == 'create':
                    rid = service.create(body.get('name'))
                elif action == 'delete':
                    expected = body.get('expected')
                    if body.get('confirm_delete') is not True or not isinstance(expected, dict) or set(expected) != {'name', 'public_key'}:
                        raise ValueError('Refresh and confirm permanent room deletion.')
                    delete_room_with_battery_guard(service, rid, expected)
                elif action == 'enabled':
                    service.set_enabled(rid, body.get('enabled'))
                elif action == 'password':
                    service.set_password(rid, body.get('password'))
                elif action == 'grant':
                    # Administration is dashboard-local, not remote CLI access.
                    if body.get('role') not in ('reader', 'writer'):
                        raise ValueError('Choose reader or writer.')
                    service.grant(rid, body.get('key'), body.get('role'))
                elif action == 'revoke':
                    service.revoke(rid, body.get('key'))
                elif action == 'post':
                    service.local_post(rid, body.get('text'))
                elif action == 'bot':
                    result = bridge.request({'operation':'room_bot','room':rid}, timeout=20)
                    if not result.get('ok'):
                        raise ValueError(result.get('error','Could not select room as bot channel.'))
                elif action == 'restart':
                    result = bridge.request({'operation':'room_restart'}, timeout=20)
                    if not result.get('ok'):
                        raise ValueError(result.get('error','Room restart failed.'))
                else:
                    raise ValueError('Unknown action.')
            worker = getattr(bridge.runtime, 'rooms', None)
            status = worker.status() if worker else dict(running=False,error='Room worker unavailable; connect the companion.',sessions=0,dropped_packets=0)
            rooms = []
            for detail in service.snapshot():
                detail['contact_uri'] = 'meshcore://contact/add?' + urlencode(dict(name=detail['name'],public_key=detail['public_key'],type=3))
                rooms.append(detail)
            return reply(dict(ok=True, rooms=rooms, status=status))
        except (ValueError, TypeError, KeyError, PermissionError) as exc:
            return reply(dict(ok=False,error=str(exc)),400)
        except (sqlite3.Error, OSError) as exc:
            return reply(dict(ok=False,error='Room service unavailable: '+str(exc)),503)
