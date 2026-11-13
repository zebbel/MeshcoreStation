from meshcorestation.storage.connection import connect as open_database
"""Short-lived, read-only connections to the bot's existing SQLite database."""
import hashlib
import json
import sqlite3
from contextlib import closing

from meshcorestation.config import DB_PATH, TIMEZONE
PAGE_SIZE = 200


def timestamp(value, preferences=None):
    if value is None:
        from meshcorestation.web.i18n import t
        return t("Not recorded")
    try:
        from meshcorestation.display import format_datetime
        return format_datetime(value, preferences=preferences) + " " + TIMEZONE.key
    except (ValueError, TypeError, OverflowError, OSError):
        return str(value)


def bot_status():
    # Read in-process connection state instead of polling another systemd unit.
    from meshcorestation.bridge import bridge
    return bridge.status


def snapshot(command=None, limit=PAGE_SIZE):
    with closing(open_database(DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        count = db.execute("SELECT COUNT(*) FROM repeaters").fetchone()[0]
        latest = db.execute("SELECT * FROM logger ORDER BY recv_time DESC, id DESC LIMIT 1").fetchone()
        return dict(_history_rows(db, command, limit), repeaters=count, latest=dict(latest) if latest else None)


def _history_rows(db, command, limit):
    commands = [row[0] for row in db.execute(
        "SELECT DISTINCT message FROM logger WHERE message IS NOT NULL ORDER BY message COLLATE NOCASE, message")]
    where, params = (" WHERE message = ?", [command]) if command is not None else ("", [])
    total = db.execute("SELECT COUNT(*) FROM logger" + where, params).fetchone()[0]
    rows = db.execute("SELECT * FROM logger" + where + " ORDER BY recv_time DESC, id DESC LIMIT ?",
                      params + [limit]).fetchall()
    return {"commands": commands, "total": total, "rows": [dict(row) for row in reversed(rows)]}


def history_snapshot(command, limit, previous):
    from meshcorestation.display import settings
    from meshcorestation.web.i18n import language

    with closing(sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        revision = db.execute("SELECT revision FROM command_history_revision WHERE id=1").fetchone()[0]
        preferences = settings(db)
        token = hashlib.sha256(json.dumps(
            [revision, command, limit, TIMEZONE.key, preferences, language()], sort_keys=True).encode()).hexdigest()
        if token == previous:
            return None
        return dict(_history_rows(db, command, limit), preferences=preferences, token=token)


def overview():
    """Small, indexed dashboard summary; never fetch the history table to render cards."""
    with closing(open_database(DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        count = db.execute("SELECT COUNT(*) FROM repeaters").fetchone()[0]
        latest = db.execute("SELECT id, message, sender, recv_time FROM logger ORDER BY recv_time DESC, id DESC LIMIT 1").fetchone()
        return {"repeaters": count, "latest": dict(latest) if latest else None}
