"""Persistent display preferences; timezone and scheduler configuration stay separate."""
import sqlite3
import os
import threading
from functools import lru_cache
from datetime import datetime
from meshcorestation.config import DATA_DIR, TIMEZONE

DEFAULTS = {'date_format': 'german', 'hour_format': '24'}
LOCK = threading.Lock()


def validate(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULTS)
            or value['date_format'] not in ('german', 'iso', 'us')
            or value['hour_format'] not in ('12', '24')):
        raise ValueError('Choose German, ISO or US dates and a 12- or 24-hour clock.')
    return dict(value)


def settings():
    from meshcorestation.storage.connection import connect
    from meshcorestation.config import DB_PATH
    from contextlib import closing
    try:
        with closing(connect(DB_PATH.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
            row=db.execute('SELECT date_format,hour_format FROM application_preferences WHERE id=1').fetchone()
            return validate(dict(row))
    except (OSError,ValueError,TypeError,sqlite3.Error):return dict(DEFAULTS)


def save(value):
    value=validate(value)
    from meshcorestation.storage.connection import connect
    from meshcorestation.config import DB_PATH
    from contextlib import closing
    with LOCK,closing(connect(DB_PATH.as_uri()+'?mode=rw',uri=True,timeout=2)) as db,db:
        db.execute('UPDATE application_preferences SET date_format=?,hour_format=? WHERE id=1',(value['date_format'],value['hour_format']))
    return value


def format_datetime(value, zone=TIMEZONE, *, time_only=False):
    preferences = settings()
    date = value if isinstance(value, datetime) else datetime.fromtimestamp(float(value), zone)
    date = date.astimezone(zone)
    clock = date.strftime('%I:%M:%S %p' if preferences['hour_format'] == '12' else '%H:%M:%S')
    pattern = {'german':'%d.%m.%Y', 'iso':'%Y-%m-%d', 'us':'%m/%d/%Y'}[preferences['date_format']]
    return (clock if time_only else date.strftime(pattern) + ' ' + clock)
