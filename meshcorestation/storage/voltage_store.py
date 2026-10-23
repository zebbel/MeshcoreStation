"""SQLite storage shared by bot and dashboard; never contains channel secrets."""
import math
import re
from meshcorestation import battery_templates
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIELDS = ('enabled', 'public_key', 'interval_minutes', 'reports_enabled', 'report_time_1', 'report_time_2', 'timezone', 'voltage_channel', 'report_target', 'report_template', 'temperature_channel')


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS voltage_config (
      id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
      public_key TEXT NOT NULL DEFAULT '', interval_minutes INTEGER NOT NULL DEFAULT 30,
      reports_enabled INTEGER NOT NULL DEFAULT 1,
      report_time_1 TEXT NOT NULL DEFAULT '08:00', report_time_2 TEXT NOT NULL DEFAULT '20:00',
      timezone TEXT NOT NULL DEFAULT 'Europe/Berlin', voltage_channel INTEGER NOT NULL DEFAULT 1,
      report_target TEXT NOT NULL DEFAULT 'bot',
      revision INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL DEFAULT 0,
      request_seq INTEGER NOT NULL DEFAULT 0, handled_seq INTEGER NOT NULL DEFAULT 0);
    INSERT OR IGNORE INTO voltage_config (id) VALUES (1);
    CREATE TABLE IF NOT EXISTS voltage_samples (
      id INTEGER PRIMARY KEY, public_key TEXT NOT NULL, name TEXT NOT NULL,
      sampled_at REAL NOT NULL, voltage REAL, error TEXT,
      voltage_channel INTEGER NOT NULL, interval_seconds INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS voltage_samples_key_time ON voltage_samples(public_key, sampled_at);
    CREATE TABLE IF NOT EXISTS voltage_reports (
      slot TEXT PRIMARY KEY, public_key TEXT NOT NULL, due_at REAL NOT NULL,
      attempted_at REAL NOT NULL, channel_name TEXT, status TEXT NOT NULL, detail TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS voltage_worker (
      id INTEGER PRIMARY KEY CHECK(id=1), heartbeat REAL NOT NULL, state TEXT NOT NULL);
    ''')
    # Keep the previous bot-chat destination for existing installations.
    if 'report_target' not in {row[1] for row in db.execute('PRAGMA table_info(voltage_config)')}:
        db.execute("ALTER TABLE voltage_config ADD COLUMN report_target TEXT NOT NULL DEFAULT 'bot'")

    if 'report_template' not in {row[1] for row in db.execute('PRAGMA table_info(voltage_config)')}:
        db.execute("ALTER TABLE voltage_config ADD COLUMN report_template TEXT NOT NULL DEFAULT 'Battery {repeater_name}: {reading} | {sample_time}'")

    # Add optional telemetry fields in place; legacy voltage rows keep their IDs
    # and values, and NULL temperature means it was never measured.
    if 'temperature_channel' not in {row[1] for row in db.execute('PRAGMA table_info(voltage_config)')}:
        db.execute('ALTER TABLE voltage_config ADD COLUMN temperature_channel INTEGER NOT NULL DEFAULT 1')
    sample_columns = {row[1] for row in db.execute('PRAGMA table_info(voltage_samples)')}
    for name, kind in (('temperature','REAL'), ('temperature_channel','INTEGER'), ('temperature_error','TEXT')):
        if name not in sample_columns:
            db.execute(f'ALTER TABLE voltage_samples ADD COLUMN {name} {kind}')
    db.execute('CREATE INDEX IF NOT EXISTS voltage_samples_temperature_time ON voltage_samples(public_key,temperature_channel,sampled_at)')

    if 'managed' not in {row[1] for row in db.execute('PRAGMA table_info(voltage_config)')}:
        db.execute('ALTER TABLE voltage_config ADD COLUMN managed INTEGER NOT NULL DEFAULT 1')
    # Upgrade the singleton table in place, preserving settings and pending reads.
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name='voltage_config'").fetchone()[0]
    if re.search(r'CHECK\s*\(\s*id\s*=\s*1\s*\)', sql, re.I):
        columns = ','.join(row[1] for row in db.execute('PRAGMA table_info(voltage_config)'))
        with db:
            db.execute('ALTER TABLE voltage_config RENAME TO voltage_config_single')
            db.execute(re.sub(r'CHECK\s*\(\s*id\s*=\s*1\s*\)', '', sql, flags=re.I))
            db.execute(f'INSERT INTO voltage_config ({columns}) SELECT {columns} FROM voltage_config_single')
            db.execute('DROP TABLE voltage_config_single')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS voltage_config_key ON voltage_config(public_key) WHERE public_key != ''")
    # Keep existing report attempts reserved after namespacing slots by repeater.
    db.execute("UPDATE voltage_reports SET slot=public_key||'|'||slot WHERE substr(slot,1,65) != public_key||'|'")
    db.commit()


def configurations(db):
    return [config(db, row[0]) for row in db.execute("SELECT public_key FROM voltage_config WHERE public_key != '' AND managed=1 ORDER BY id")]


def ensure_repeater(db, key):
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('Select a repeater from the list or map.')
    if not db.execute('SELECT 1 FROM repeaters WHERE lower(public_key)=? AND adv_type=2', (key,)).fetchone():
        raise ValueError('Selected repeater is not in the known repeater list.')
    db.execute('INSERT OR IGNORE INTO voltage_config(public_key) VALUES (?)', (key,))
    db.execute('UPDATE voltage_config SET managed=1 WHERE public_key=?', (key,))
    return config(db, key)


def config(db, public_key=None):
    if public_key:
        row = db.execute('SELECT * FROM voltage_config WHERE public_key=?', (public_key,)).fetchone()
        if row is None:
            return dict(id=None, public_key=public_key, enabled=False, interval_minutes=30,
                        reports_enabled=True, report_time_1='08:00', report_time_2='20:00',
                        timezone='Europe/Berlin', voltage_channel=1, temperature_channel=1, report_target='bot', report_template=battery_templates.DEFAULT,
                        revision=0, updated_at=0, request_seq=0, handled_seq=0)
    else:
        row = db.execute('SELECT * FROM voltage_config WHERE managed=1 ORDER BY public_key=\'\',id LIMIT 1').fetchone()
    if row is None:
        return dict(id=None, public_key='', enabled=False, interval_minutes=30, reports_enabled=False,
                    report_time_1='08:00', report_time_2='20:00', timezone='Europe/Berlin',
                    voltage_channel=1, temperature_channel=1, report_target='bot', report_template=battery_templates.DEFAULT, revision=0, updated_at=0, request_seq=0, handled_seq=0)
    result = dict(row)
    for key in ('enabled', 'reports_enabled'):
        result[key] = bool(result[key])
    return result


def validate(value, db):
    if (not isinstance(value, dict) or not set(FIELDS)-{'report_template','temperature_channel'} <= set(value)
            or not set(value) <= set(FIELDS)):
        raise ValueError('Invalid telemetry settings fields.')
    result = dict(value)
    for key in ('enabled', 'reports_enabled'):
        if type(result[key]) is not bool:
            raise ValueError('Invalid enable/disable setting.')
    key = result['public_key']
    if not isinstance(key, str) or (key and not re.fullmatch('[0-9a-fA-F]{64}', key)):
        raise ValueError('Select a repeater from the list or map.')
    result['public_key'] = key = key.lower()
    # Preserve saved text when an older client only edits schedules.
    saved=config(db,key)
    result.setdefault('report_template',saved['report_template'])
    result.setdefault('temperature_channel',saved['temperature_channel'])
    battery_templates.validate(result['report_template'])
    if key and not db.execute('SELECT 1 FROM repeaters WHERE lower(public_key)=? AND adv_type=2', (key,)).fetchone():
        raise ValueError('Selected repeater is not in the known repeater list.')
    if result['enabled'] and not key:
        raise ValueError('Select a repeater before enabling monitoring.')
    target = result['report_target']
    if not isinstance(target, str):
        raise ValueError('Choose a battery report destination.')
    if target == 'bot':
        pass
    elif target.startswith('room:'):
        room_id = target[5:]
        if not room_id.isdecimal() or room_id.startswith('0') or not 1 <= int(room_id) <= 2147483647:
            raise ValueError('Choose an existing room.')
    elif target.startswith('channel:'):
        name = target[8:]
        if (not name or name.strip() != name or len(name.encode('utf-8')) > 31
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
            raise ValueError('Choose a valid companion channel.')
    else:
        raise ValueError('Choose a battery report destination.')
    for field, lo, hi in (('interval_minutes', 5, 1440), ('voltage_channel', 1, 255), ('temperature_channel', 0, 255)):
        if type(result[field]) is not int or not lo <= result[field] <= hi:
            raise ValueError(f'{field} must be a whole number from {lo} to {hi}.')
    for field in ('report_time_1', 'report_time_2'):
        if not isinstance(result[field], str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', result[field]):
            raise ValueError('Report times must use HH:MM (24-hour clock).')
    if result['report_time_1'] == result['report_time_2']:
        raise ValueError('Choose two different report times.')
    try:
        if not isinstance(result['timezone'], str) or len(result['timezone']) > 100:
            raise ValueError()
        ZoneInfo(result['timezone'])
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError('Enter a valid timezone, for example Europe/Berlin.') from None
    return result


def latest(db, cfg):
    row = db.execute('''SELECT * FROM voltage_samples WHERE public_key=? AND voltage_channel=?
                        ORDER BY sampled_at DESC, id DESC LIMIT 1''',
                     (cfg['public_key'], cfg['voltage_channel'])).fetchone()
    return dict(row) if row else None


def latest_temperature(db, cfg):
    row = db.execute("""SELECT * FROM voltage_samples WHERE public_key=? AND temperature_channel=?
                        ORDER BY sampled_at DESC,id DESC LIMIT 1""",
                     (cfg['public_key'],cfg['temperature_channel'])).fetchone()
    return dict(row) if row else None


def latest_temperature_reading(db, cfg):
    """Last successful saved temperature for the configured repeater/channel."""
    row = db.execute("""SELECT * FROM voltage_samples WHERE public_key=? AND temperature_channel=?
                        AND temperature IS NOT NULL AND temperature_error IS NULL
                        ORDER BY sampled_at DESC,id DESC LIMIT 1""",
                     (cfg['public_key'],cfg['temperature_channel'])).fetchone()
    return dict(row) if row else None


def latest_reading(db, cfg):
    """Last successful reading for this repeater and telemetry channel."""
    row = db.execute('''SELECT * FROM voltage_samples WHERE public_key=? AND voltage_channel=?
                        AND voltage IS NOT NULL AND error IS NULL
                        ORDER BY sampled_at DESC, id DESC LIMIT 1''',
                     (cfg['public_key'], cfg['voltage_channel'])).fetchone()
    return dict(row) if row else None


def extract_voltage(telemetry, channel):
    if not isinstance(telemetry, list):
        raise ValueError('No telemetry response from repeater.')
    matches = [r.get('value') for r in telemetry if isinstance(r, dict) and r.get('type') == 'voltage' and r.get('channel') == channel]
    if len(matches) != 1:
        available = sorted({r.get('channel') for r in telemetry if isinstance(r, dict)
                            and r.get('type') == 'voltage' and type(r.get('channel')) is int})
        raise ValueError(f'Expected one voltage on LPP channel {channel}; available voltage channels: {available}.')
    v = matches[0]
    if type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= 100:
        raise ValueError('Missing or invalid battery voltage; zero is not stored as a reading.')
    return round(float(v), 3)


def extract_temperature(telemetry, channel):
    """Optional LPP temperature in Celsius. Zero and negative values are valid."""
    if not isinstance(telemetry,list):
        raise ValueError('No telemetry response from repeater.')
    matches = [r.get('value') for r in telemetry if isinstance(r,dict)
               and r.get('type')=='temperature' and r.get('channel')==channel]
    if len(matches)!=1:
        raise ValueError(f'Expected one temperature on LPP channel {channel}; received {len(matches)}.')
    value=matches[0]
    if type(value) not in (int,float) or not math.isfinite(value) or not -273.15<=value<=1000:
        raise ValueError('Missing or invalid temperature reading.')
    return round(float(value),3)


def due_slots(cfg, now):
    """10 minute grace; no backlog. DST repeated times run once, nonexistent times skip."""
    if not cfg['enabled'] or not cfg['reports_enabled']:
        return []
    zone = ZoneInfo(cfg['timezone'])
    today = datetime.fromtimestamp(now, zone).date()
    result = []
    for value in sorted((cfg['report_time_1'], cfg['report_time_2'])):
        hour, minute = map(int, value.split(':'))
        local = datetime(today.year, today.month, today.day, hour, minute, tzinfo=zone, fold=0)
        due = local.timestamp()
        back = datetime.fromtimestamp(due, zone)
        if (back.hour, back.minute) != (hour, minute):
            continue
        if cfg['updated_at'] <= due <= now < due + 600:
            result.append((f'{cfg["timezone"]}|{today.isoformat()}|{value}', due))
    return result
