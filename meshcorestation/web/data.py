"""Short-lived, read-only connections to the bot's existing SQLite database."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from meshcorestation.config import DB_PATH, TIMEZONE
PAGE_SIZE = 200


def timestamp(value):
    if value is None:
        return "Not recorded"
    try:
        return datetime.fromtimestamp(float(value), TIMEZONE).strftime("%d.%m.%Y %H:%M:%S %Z")
    except (ValueError, TypeError, OverflowError, OSError):
        return str(value)


def bot_status():
    # Read in-process connection state instead of polling another systemd unit.
    from meshcorestation.bridge import bridge
    return bridge.status


def snapshot(command=None, limit=PAGE_SIZE):
    with closing(sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        count = db.execute("SELECT COUNT(*) FROM repeaters").fetchone()[0]
        commands = [row[0] for row in db.execute("SELECT DISTINCT message FROM logger WHERE message IS NOT NULL ORDER BY message COLLATE NOCASE, message")]
        latest = db.execute("SELECT * FROM logger ORDER BY recv_time DESC, id DESC LIMIT 1").fetchone()
        where, params = (" WHERE message = ?", [command]) if command is not None else ("", [])
        total = db.execute("SELECT COUNT(*) FROM logger" + where, params).fetchone()[0]
        rows = db.execute("SELECT * FROM logger" + where + " ORDER BY recv_time DESC, id DESC LIMIT ?", params + [limit]).fetchall()
        return {"repeaters": count, "commands": commands, "latest": dict(latest) if latest else None, "total": total, "rows": [dict(row) for row in reversed(rows)]}
