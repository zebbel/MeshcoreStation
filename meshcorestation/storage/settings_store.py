"""Shared SQLite configuration; existing values survive startup and upgrades."""
import sqlite3
from contextlib import closing


def initialize(db):
    db.execute("CREATE TABLE IF NOT EXISTS bot_settings (id INTEGER PRIMARY KEY CHECK(id=1), serial_port TEXT NOT NULL, channel_name TEXT NOT NULL)")
    db.execute("INSERT OR IGNORE INTO bot_settings VALUES (1, ?, ?)", ('/dev/ttyACM0', ''))


def read_settings(db):
    row = db.execute("SELECT serial_port, channel_name FROM bot_settings WHERE id=1").fetchone()
    return {'serial_port': row[0], 'channel_name': row[1]}
