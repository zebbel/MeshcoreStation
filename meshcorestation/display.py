"""Persistent display preferences; timezone and scheduler configuration stay separate."""
import json
import os
import threading
from functools import lru_cache
from datetime import datetime
from meshcorestation.config import DATA_DIR, TIMEZONE

FILE = DATA_DIR / 'display-settings.json'
DEFAULTS = {'date_format': 'german', 'hour_format': '24'}
LOCK = threading.Lock()


def validate(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULTS)
            or value['date_format'] not in ('german', 'iso', 'us')
            or value['hour_format'] not in ('12', '24')):
        raise ValueError('Choose German, ISO or US dates and a 12- or 24-hour clock.')
    return dict(value)


@lru_cache(maxsize=8)
def _load(path, modified):
    return validate(json.loads(path.read_text(encoding='utf-8')))


def settings():
    try:
        return dict(_load(FILE, FILE.stat().st_mtime_ns))
    except (OSError, ValueError, TypeError):
        return dict(DEFAULTS)


def save(value):
    value = validate(value)
    with LOCK:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = FILE.with_suffix('.tmp')
        temporary.write_text(json.dumps(value), encoding='utf-8')
        os.replace(temporary, FILE)
    return value


def format_datetime(value, zone=TIMEZONE, *, time_only=False):
    preferences = settings()
    date = value if isinstance(value, datetime) else datetime.fromtimestamp(float(value), zone)
    date = date.astimezone(zone)
    clock = date.strftime('%I:%M:%S %p' if preferences['hour_format'] == '12' else '%H:%M:%S')
    pattern = {'german':'%d.%m.%Y', 'iso':'%Y-%m-%d', 'us':'%m/%d/%Y'}[preferences['date_format']]
    return (clock if time_only else date.strftime(pattern) + ' ' + clock)
