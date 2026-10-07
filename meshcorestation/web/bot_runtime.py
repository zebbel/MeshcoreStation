"""Serial configuration remains accessible when the companion is offline."""
import json
import sqlite3
from contextlib import closing
from serial.tools import list_ports
from meshcorestation.web.data import DB_PATH
from meshcorestation.storage.settings_store import initialize, read_settings


def ports():
    return [{'device': p.device, 'description': p.description or p.device} for p in sorted(list_ports.comports(), key=lambda p: p.device)]


def runtime_request(request):
    try:
        available = ports()
        with closing(sqlite3.connect(DB_PATH.as_uri() + '?mode=rw', uri=True, timeout=5)) as db:
            with db:
                initialize(db)
            if request.method == 'GET':
                return {'ok': True, 'settings': read_settings(db), 'ports': available}, 200
            if request.mimetype != 'application/json':
                return {'ok': False, 'error': 'Expected JSON.'}, 415
            raw = request.stream.read(4097)
            if len(raw) > 4096:
                raise ValueError('Request too large')
            payload = json.loads(raw)
            if not isinstance(payload, dict) or set(payload) != {'serial_port', 'expected_serial_port'}:
                raise ValueError('Refresh serial settings before saving')
            selected = payload['serial_port']
            if not isinstance(selected, str) or selected not in {p['device'] for p in available}:
                raise ValueError('Select an available serial port; refresh if a device was unplugged')
            db.execute('BEGIN IMMEDIATE')
            before = read_settings(db)
            if payload['expected_serial_port'] != before['serial_port']:
                db.rollback()
                return {'ok': False, 'error': 'Serial settings changed. Refresh before saving.'}, 409
            db.execute('UPDATE bot_settings SET serial_port=? WHERE id=1', (selected,))
            db.commit()
        # Reconnect in this process; the web server stays available during setup.
        from meshcorestation.bridge import bridge
        bridge.reconnect()
        return {'ok': True, 'message': 'Serial port saved; reconnect requested. Check Running status to confirm connection.'}, 200
    except (ValueError, TypeError):
        return {'ok': False, 'error': 'Invalid serial settings. Refresh and select an available port.'}, 400
    except (OSError, RuntimeError):
        return {'ok': False, 'error': 'Restart outcome could not be confirmed. The serial setting may be saved; refresh and check bot status.'}, 503
    except sqlite3.Error:
        return {'ok': False, 'error': 'Cannot update the bot database. Check MESHCORESTATION_DATA_DIR and write permissions for the same Linux user.'}, 503
