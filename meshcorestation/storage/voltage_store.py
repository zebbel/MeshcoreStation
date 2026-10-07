"""SQLite storage shared by bot and dashboard; never contains channel secrets."""
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIELDS = ('enabled', 'public_key', 'interval_minutes', 'reports_enabled', 'report_time_1', 'report_time_2', 'timezone', 'voltage_channel')


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS voltage_config (
      id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
      public_key TEXT NOT NULL DEFAULT '', interval_minutes INTEGER NOT NULL DEFAULT 30,
      reports_enabled INTEGER NOT NULL DEFAULT 1,
      report_time_1 TEXT NOT NULL DEFAULT '08:00', report_time_2 TEXT NOT NULL DEFAULT '20:00',
      timezone TEXT NOT NULL DEFAULT 'Europe/Berlin', voltage_channel INTEGER NOT NULL DEFAULT 1,
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


def config(db):
    row = db.execute('SELECT * FROM voltage_config WHERE id=1').fetchone()
    if row is None:
        raise ValueError('Start the updated bot once to initialize voltage monitoring.')
    result = dict(row)
    for key in ('enabled', 'reports_enabled'):
        result[key] = bool(result[key])
    return result


def validate(value, db):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError('Invalid voltage settings fields.')
    result = dict(value)
    for key in ('enabled', 'reports_enabled'):
        if type(result[key]) is not bool:
            raise ValueError('Invalid enable/disable setting.')
    key = result['public_key']
    if not isinstance(key, str) or (key and not re.fullmatch('[0-9a-fA-F]{64}', key)):
        raise ValueError('Select a repeater from the list or map.')
    result['public_key'] = key = key.lower()
    if key and not db.execute('SELECT 1 FROM repeaters WHERE lower(public_key)=? AND adv_type=2', (key,)).fetchone():
        raise ValueError('Selected repeater is not in the known repeater list.')
    if result['enabled'] and not key:
        raise ValueError('Select a repeater before enabling monitoring.')
    for field, lo, hi in (('interval_minutes', 5, 1440), ('voltage_channel', 1, 255)):
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
