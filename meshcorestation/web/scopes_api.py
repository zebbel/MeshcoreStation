"""Manage the saved reply scopes with transactional, conflict-checked edits."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from meshcorestation.config import DB_PATH


def snapshot(db):
    scopes = [dict(row) for row in db.execute('SELECT name,scope_key FROM scopes ORDER BY name')]
    revision = hashlib.sha256(json.dumps(scopes, sort_keys=True).encode()).hexdigest()
    return {'ok': True, 'scopes': scopes, 'revision': revision}


def scopes_request(request):
    try:
        with closing(sqlite3.connect(DB_PATH.as_uri() + '?mode=rw', uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            if request.method == 'GET':
                return snapshot(db), 200
            if request.mimetype != 'application/json':
                return {'ok': False, 'error': 'Expected JSON.'}, 415
            raw = request.stream.read(4097)
            if len(raw) > 4096:
                raise ValueError('Request too large.')
            value = json.loads(raw)
            if not isinstance(value, dict) or value.get('operation') not in {'add', 'edit', 'delete'}:
                raise ValueError('Unknown scope operation.')
            with db:
                # Reserve the write before checking the snapshot, including chat-command changes.
                db.execute('BEGIN IMMEDIATE')
                before = snapshot(db)
                if value.get('expected_revision') != before['revision']:
                    return {'ok': False, 'error': 'Scopes changed. Reload before saving.'}, 409
                operation = value['operation']
                original = value.get('original_name')
                if operation != 'add' and (not isinstance(original, str) or not any(s['name'] == original for s in before['scopes'])):
                    raise ValueError('Select an existing scope.')
                if operation == 'delete':
                    if value.get('confirm_delete') is not True:
                        raise ValueError('Confirm scope deletion.')
                    db.execute('DELETE FROM scopes WHERE name=?', (original,))
                else:
                    name = value.get('name')
                    if not isinstance(name, str):
                        raise ValueError('Enter a scope name.')
                    name = name.strip().removeprefix('#')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,30}', name):
                        raise ValueError('Use 1–30 letters, digits, hyphens or underscores.')
                    # Keep the same derivation as the existing scope add chat command.
                    key = hashlib.sha256(('#' + name).encode()).digest()[:16].hex()
                    if operation == 'add':
                        db.execute('INSERT INTO scopes (name,scope_key) VALUES (?,?)', (name, key))
                    else:
                        db.execute('UPDATE scopes SET name=?,scope_key=? WHERE name=?', (name, key, original))
                result = snapshot(db)
            return result, 200
    except sqlite3.IntegrityError:
        return {'ok': False, 'error': 'A scope with that name already exists.'}, 409
    except (ValueError, TypeError) as exc:
        return {'ok': False, 'error': str(exc)}, 400
    except sqlite3.Error:
        return {'ok': False, 'error': 'Scope database unavailable. Check MeshcoreStation status and permissions.'}, 503
