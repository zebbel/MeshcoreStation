"""Command editor snapshots, conflict-checked saves and radio-free previews."""
import json
import sqlite3
from contextlib import closing
from meshcorestation.config import DB_PATH
from meshcorestation.storage.command_store import snapshot, validate, replace
from meshcorestation.commands.templates import render, example_data, public_catalog, MAX_COMMANDS, MAX_TEMPLATE_BYTES


def commands_request(request):
    try:
        with closing(sqlite3.connect(DB_PATH.as_uri() + '?mode=rw', uri=True, timeout=5)) as db:
            before = snapshot(db)
            if request.method == 'GET':
                return {**before, 'placeholders': public_catalog(), 'max_commands': MAX_COMMANDS, 'max_template_bytes': MAX_TEMPLATE_BYTES}, 200
            if request.mimetype != 'application/json':
                return {'ok': False, 'error': 'Expected JSON.'}, 415
            raw = request.stream.read(65537)
            if len(raw) > 65536:
                raise ValueError('Request too large.')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError('Invalid request.')
            if data.get('operation') == 'preview':
                commands = validate(data.get('commands'), before['commands'])
                samples = example_data(commands)
                selected = next((item for item in commands if item['id'] == data.get('selected_id')), commands[0])
                samples['command'] = selected['trigger']
                return {'ok': True, 'reply': render(selected['reply'], samples), 'failure_reply': render(selected.get('failure_reply', '{result}'), {**samples, 'result': 'Position unavailable or scope already exists.', 'latitude': None, 'longitude': None, 'altitude': None}) if selected['action'] != 'reply' else '', 'help_reply': render(commands[0]['reply'], samples)}, 200
            if data.get('operation') != 'save':
                raise ValueError('Unknown operation.')
            with db:
                result = replace(db, data.get('commands'), data.get('expected_revision'))
            return result, 200
    except RuntimeError as exc:
        return {'ok': False, 'error': str(exc)}, 409
    except (ValueError, TypeError, KeyError) as exc:
        return {'ok': False, 'error': str(exc)}, 400
    except sqlite3.Error:
        return {'ok': False, 'error': 'Command database unavailable. Check MeshcoreStation status.'}, 503
