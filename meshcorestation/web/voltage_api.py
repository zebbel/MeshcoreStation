"""Short database requests; radio polling happens asynchronously in the bot."""
import json
import sqlite3
import time
from contextlib import closing
from meshcorestation.web.data import DB_PATH
from meshcorestation.storage.voltage_store import FIELDS, config, configurations, ensure_repeater, validate, latest
from meshcorestation.config import DATA_DIR
from meshcorestation.rooms.service import RoomService
from meshcorestation import battery_templates


def payload(db, selected_key, days):
    cfg = config(db, selected_key)
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
    reports = [dict(r) for r in db.execute('SELECT * FROM voltage_reports WHERE public_key=? ORDER BY attempted_at DESC LIMIT 6', (key,))]
    rooms = [{'id': r['id'], 'name': r['name'], 'enabled': bool(r['enabled'])} for r in RoomService(DATA_DIR / 'rooms.db').rooms()]
    managed_keys = [c['public_key'] for c in configurations(db)]
    from meshcorestation.storage import passive_stats
    with closing(passive_stats.connect()) as stats_db:
        managed_keys = list(dict.fromkeys(managed_keys + [row[0] for row in stats_db.execute(
            "SELECT public_key FROM subscriptions UNION SELECT public_key FROM selection WHERE public_key != ''")]))
    return {'ok': True, 'config': cfg, 'repeaters': repeaters, 'managed_repeaters': managed_keys, 'history_key': key,
            'samples': samples, 'latest': latest(db, dict(cfg, public_key=key)),
            'bot_channel': row['channel_name'] if row else None, 'rooms': rooms,
            'worker': dict(worker) if worker else None, 'reports': reports, 'server_time': time.time(),
            'report_placeholders': battery_templates.catalog(),
            'report_default': battery_templates.DEFAULT}


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
            if request.content_length is not None and request.content_length > 8192:
                raise ValueError('Request too large.')
            # Use the shared request cache so middleware cannot consume a POST body first.
            raw = request.get_data(cache=True)
            if len(raw) > 8192:
                raise ValueError('Request too large.')
            body = json.loads(raw)
            if not isinstance(body, dict) or body.get('operation') not in {'save', 'sample', 'add', 'remove'}:
                raise ValueError('Unknown voltage operation.')
            with db:
                db.execute('BEGIN IMMEDIATE')
                value_body = body.get('value')
                if value_body is not None and not isinstance(value_body, dict):
                    raise ValueError('Invalid voltage settings fields.')
                key = body.get('public_key') or request.args.get('public_key') or (value_body or {}).get('public_key')
                if key is not None and not isinstance(key, str):
                    raise ValueError('Select a repeater.')
                key = key.lower() if key else None
                if body['operation'] == 'remove':
                    if not key:
                        raise ValueError('Select a repeater to remove.')
                    from meshcorestation.storage import passive_stats
                    # Keep only a disabled identity/revision tombstone to reject in-flight work.
                    db.execute('''UPDATE voltage_config SET managed=0,enabled=0,reports_enabled=0,
                        request_seq=0,handled_seq=0,revision=revision+1,interval_minutes=30,
                        report_time_1='08:00',report_time_2='20:00',timezone='Europe/Berlin',
                        voltage_channel=1,report_target='bot',report_template='Battery {repeater_name}: {reading} | {sample_time}',updated_at=? WHERE public_key=?''', (time.time(), key))
                    db.execute('DELETE FROM voltage_samples WHERE public_key=?', (key,))
                    db.execute('DELETE FROM voltage_reports WHERE public_key=?', (key,))
                    with closing(passive_stats.connect()) as stats_db, stats_db:
                        stats_db.execute('DELETE FROM subscriptions WHERE public_key=?', (key,))
                        stats_db.execute('DELETE FROM observations WHERE target=?', (key,))
                        stats_db.execute("UPDATE selection SET public_key='' WHERE public_key=?", (key,))
                    # Removing a managed repeater must also erase its optimizer
                    # role, scheduled neighbor reads, snapshots and audit history.
                    # Network-wide passive observations remain because other
                    # repeaters still depend on those common packet records.
                    from meshcorestation.storage import optimizer_store, advisor_history
                    optimizer_store.remove_repeater(key)
                    advisor_history.remove_repeater(key)
                    return {'ok': True}, 200
                if body['operation'] == 'add':
                    cfg = ensure_repeater(db, key)
                    from meshcorestation.storage import passive_stats
                    passive_stats.track(key)
                    return {'ok': True, 'config': cfg}, 200
                cfg = config(db, key)
                if type(body.get('expected_revision')) is not int or body['expected_revision'] != cfg['revision']:
                    return {'ok': False, 'error': 'Settings changed. Refresh before saving or reading.'}, 409
                if body['operation'] == 'save':
                    value = validate(body.get('value'), db)
                    if value['report_target'].startswith('room:'):
                        room = RoomService(DATA_DIR / 'rooms.db').config(int(value['report_target'][5:]))
                        if not room['enabled']:
                            raise ValueError('Enable the chosen room before selecting it for reports.')
                    if key and value['public_key'] != key:
                        raise ValueError('Selected repeater changed. Reload its settings.')
                    cfg = ensure_repeater(db, value['public_key'])
                    assignments = ','.join(f'{field}=?' for field in FIELDS)
                    db.execute(f'UPDATE voltage_config SET {assignments},revision=revision+1,updated_at=?,handled_seq=request_seq WHERE id=?',
                               [value[f] for f in FIELDS] + [time.time(), cfg['id']])
                else:
                    if not cfg['public_key'] or cfg['id'] is None or not cfg.get('managed', 1):
                        raise ValueError('Save a repeater selection first.')
                    worker = db.execute('SELECT * FROM voltage_worker WHERE id=1').fetchone()
                    if not worker or worker['state'] == 'stopped' or time.time() - worker['heartbeat'] > 150:
                        raise ValueError('Bot monitor is offline. Start the connected bot before requesting a reading.')
                    previous = latest(db, cfg)
                    if cfg['request_seq'] > cfg['handled_seq'] or (previous and time.time() - previous['sampled_at'] < 60):
                        raise ValueError('A reading is pending or was just completed. Wait one minute before reading again.')
                    if worker['state'] == 'reading telemetry':
                        raise ValueError('A telemetry request is already running.')
                    db.execute('UPDATE voltage_config SET request_seq=request_seq+1 WHERE id=?', (cfg['id'],))
            return {'ok': True, 'config': config(db, cfg['public_key'])}, 200
    except (ValueError, TypeError) as exc:
        return {'ok': False, 'error': str(exc)}, 400
    except sqlite3.Error:
        return {'ok': False, 'error': 'Voltage database unavailable. Start the updated bot once; check MESHCORESTATION_DATA_DIR and permissions.'}, 503


def register_battery_template_routes(server):
    from flask import request
    from meshcorestation.web.http import control_request_error, json_response
    from meshcorestation import battery_templates
    @server.post('/api/battery-report-preview')
    def preview():
        if control_request_error():
            return json_response({'ok':False,'error':'Open from the local dashboard.'},403)
        try:
            if request.mimetype != 'application/json' or (request.content_length or 0)>4096:
                raise ValueError('Expected a report template.')
            data=request.get_json()
            text=battery_templates.preview(data.get('template'))
            return json_response({'ok':True,'preview':text})
        except (ValueError,TypeError,AttributeError) as error:
            return json_response({'ok':False,'error':str(error)},400)
