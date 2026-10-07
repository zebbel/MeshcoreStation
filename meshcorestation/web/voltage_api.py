"""Short database requests; radio polling happens asynchronously in the bot."""
import json
import sqlite3
import time
from contextlib import closing
from meshcorestation.web.data import DB_PATH
from meshcorestation.storage.voltage_store import FIELDS, config, validate, latest


def payload(db, selected_key, days):
    cfg = config(db)
    key = selected_key or cfg['public_key']
    repeaters = [dict(r) for r in db.execute('''SELECT lower(public_key) AS public_key,
        name, latitude, longitude FROM repeaters WHERE adv_type=2
        ORDER BY name COLLATE NOCASE, public_key''')]
    if key and key not in {r['public_key'] for r in repeaters}:
        raise ValueError('Unknown repeater.')
    samples = [dict(r) for r in db.execute('''SELECT sampled_at,voltage,error,voltage_channel,interval_seconds
        FROM voltage_samples WHERE public_key=? AND voltage_channel=? AND sampled_at>=?
        ORDER BY sampled_at DESC, id DESC LIMIT 9000''', (key, cfg['voltage_channel'], time.time() - days * 86400))]
    samples.reverse()
    row = db.execute('SELECT channel_name FROM bot_settings WHERE id=1').fetchone()
    worker = db.execute('SELECT * FROM voltage_worker WHERE id=1').fetchone()
    reports = [dict(r) for r in db.execute('SELECT * FROM voltage_reports ORDER BY attempted_at DESC LIMIT 6')]
    return {'ok': True, 'config': cfg, 'repeaters': repeaters, 'history_key': key,
            'samples': samples, 'latest': latest(db, dict(cfg, public_key=key)),
            'bot_channel': row['channel_name'] if row else None,
            'worker': dict(worker) if worker else None, 'reports': reports, 'server_time': time.time()}


def voltage_request(request):
    try:
        with closing(sqlite3.connect(DB_PATH.as_uri() + '?mode=rw', uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            if request.method == 'GET':
                days = request.args.get('days', '7')
                if days not in {'1', '7', '30'}:
                    raise ValueError('Choose 1, 7 or 30 days.')
                db.execute('BEGIN')
                return payload(db, request.args.get('public_key', '').lower(), int(days)), 200
            if request.mimetype != 'application/json':
                return {'ok': False, 'error': 'Expected JSON.'}, 415
            raw = request.stream.read(8193)
            if len(raw) > 8192:
                raise ValueError('Request too large.')
            body = json.loads(raw)
            if not isinstance(body, dict) or body.get('operation') not in {'save', 'sample'}:
                raise ValueError('Unknown voltage operation.')
            with db:
                db.execute('BEGIN IMMEDIATE')
                cfg = config(db)
                if type(body.get('expected_revision')) is not int or body['expected_revision'] != cfg['revision']:
                    return {'ok': False, 'error': 'Settings changed. Refresh before saving or reading.'}, 409
                if body['operation'] == 'save':
                    value = validate(body.get('value'), db)
                    assignments = ','.join(f'{field}=?' for field in FIELDS)
                    db.execute(f'UPDATE voltage_config SET {assignments},revision=revision+1,updated_at=?,handled_seq=request_seq WHERE id=1',
                               [value[f] for f in FIELDS] + [time.time()])
                else:
                    if not cfg['public_key']:
                        raise ValueError('Save a repeater selection first.')
                    worker = db.execute('SELECT * FROM voltage_worker WHERE id=1').fetchone()
                    if not worker or worker['state'] == 'stopped' or time.time() - worker['heartbeat'] > 150:
                        raise ValueError('Bot monitor is offline. Start the connected bot before requesting a reading.')
                    previous = latest(db, cfg)
                    if cfg['request_seq'] > cfg['handled_seq'] or (previous and time.time() - previous['sampled_at'] < 60):
                        raise ValueError('A reading is pending or was just completed. Wait one minute before reading again.')
                    if worker['state'] == 'reading telemetry':
                        raise ValueError('A telemetry request is already running.')
                    db.execute('UPDATE voltage_config SET request_seq=request_seq+1 WHERE id=1')
            return {'ok': True, 'config': config(db)}, 200
    except (ValueError, TypeError) as exc:
        return {'ok': False, 'error': str(exc)}, 400
    except sqlite3.Error:
        return {'ok': False, 'error': 'Voltage database unavailable. Start the updated bot once; check MESHCORESTATION_DATA_DIR and permissions.'}, 503
