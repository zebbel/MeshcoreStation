"""Create the shared schema and store commands, repeaters, positions, and scopes."""
from pathlib import Path
import sqlite3
from meshcorestation.storage.settings_store import initialize, read_settings
import time
import hashlib
import re

from meshcorestation.config import DB_PATH as DB_FILE
ADV_TYPE_REPEATER = 2

class Database:
    def __init__(self, logger):
        self.logger = logger
        from meshcorestation.storage.connection import connect
        from meshcorestation.storage import registry
        DB_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not DB_FILE.exists():DB_FILE.touch(mode=0o600)
        with sqlite3.connect(DB_FILE) as check:
            if check.execute("SELECT 1 FROM sqlite_master WHERE name='repeaters' AND type='table'").fetchone():
                raise ValueError('V5 requires a fresh data directory; V3/V4 databases are not migrated.')
        self.known_path=DB_FILE.with_name('knownRepeaters.db')
        registry.initialize(self.known_path)
        self.db = connect(DB_FILE)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.create_database()

        self.logger.info(f"SQLite database: {DB_FILE}")
        self.logger.info(f"Known repeaters : {self.get_repeater_count()}")

################################################
# DATABASE FUNCTIONS
################################################

    def close(self):
        self.db.close()
        self.logger.info("SQLite database closed.")

    def get_bot_settings(self):
        return read_settings(self.db)

    def set_bot_channel(self, name):
        with self.db:
            self.db.execute("UPDATE bot_settings SET channel_name=? WHERE id=1", (name,))

    def create_database(self):
        from meshcorestation.storage.command_store import initialize as initialize_commands
        initialize_commands(self.db)
        initialize(self.db)
        self.db.execute("CREATE TABLE IF NOT EXISTS application_meta(id INTEGER PRIMARY KEY CHECK(id=1),generation INTEGER NOT NULL CHECK(generation=5))")
        self.db.execute('INSERT OR IGNORE INTO application_meta VALUES(1,5)')
        self.db.execute("CREATE TABLE IF NOT EXISTS application_preferences(id INTEGER PRIMARY KEY CHECK(id=1),date_format TEXT NOT NULL DEFAULT 'german',hour_format TEXT NOT NULL DEFAULT '24')")
        self.db.execute('INSERT OR IGNORE INTO application_preferences(id) VALUES(1)')
        self.db.execute("CREATE TABLE IF NOT EXISTS companion_positions(public_key TEXT PRIMARY KEY,name TEXT NOT NULL,latitude REAL NOT NULL,longitude REAL NOT NULL,altitude REAL,updated_at INTEGER NOT NULL,is_bot INTEGER NOT NULL DEFAULT 0)")
        self.db.execute("CREATE TABLE IF NOT EXISTS scopes(name TEXT PRIMARY KEY,scope_key TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS management_audit(id INTEGER PRIMARY KEY,public_key TEXT NOT NULL,at REAL NOT NULL,field TEXT NOT NULL,before_value TEXT,after_value TEXT,status TEXT NOT NULL)")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS logger (
                id INTEGER PRIMARY KEY,
                sender_timestamp INTEGER,
                recv_time INTEGER,
                type TEXT,
                channel_idx INTEGER,
                channel_hash TEXT,
                channel_name TEXT,
                sender TEXT,
                message TEXT,
                path TEXT,
                rx_path TEXT,
                path_len INTEGER,
                path_hash_mode INTEGER,
                path_hash_size INTEGER,
                rssi INTEGER,
                snr REAL,
                txt_type INTEGER,
                attempt INTEGER,
                route_type INTEGER,
                payload_type INTEGER,
                payload_ver INTEGER,
                transport_code TEXT,
                pkt_hash INTEGER,
                msg_hash INTEGER,
                raw_hex TEXT,
                scope_name TEXT,
                reply TEXT,
                sender_public_key TEXT,
                sender_latitude REAL,
                sender_longitude REAL,
                sender_altitude REAL,
                sender_position_updated_at INTEGER,
                command_status TEXT
            )""")
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_logger_recv_time ON logger(recv_time)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_logger_message_time ON logger(message,recv_time DESC,id DESC)')
        from meshcorestation.storage.reply_store import initialize as initialize_replies
        from meshcorestation.storage.reception_store import initialize as initialize_receptions
        from meshcorestation.storage.voltage_store import initialize as initialize_telemetry
        initialize_replies(self.db);initialize_receptions(self.db);initialize_telemetry(self.db)
        self.db.commit()

################################################
# LOGGER FUNCTIONS
################################################

    def add_logger(self, message_data, matched_rx, scope_name, reply):
        rx = matched_rx if matched_rx is not None else {}

        shared_fields = "sender_timestamp recv_time path_len txt_type attempt".split()
        message_fields = "type channel_idx message path path_hash_mode command_status".split()
        rx_fields = "path_hash_size route_type payload_type payload_ver transport_code pkt_hash msg_hash raw_hex".split()

        data = {field: message_data.get(field) for field in message_fields}
        data.update({field: message_data.get(field) if message_data.get(field) is not None else rx.get(field) for field in shared_fields})
        data.update({field: rx.get(field) for field in rx_fields})

        data["sender"] = message_data.get("name")
        data["rssi"] = message_data.get("RSSI") if message_data.get("RSSI") is not None else rx.get("rssi")
        data["snr"] = message_data.get("SNR") if message_data.get("SNR") is not None else rx.get("snr")
        data["rx_path"] = rx.get("path")
        data["channel_hash"] = rx.get("channel_hash") or rx.get("chan_hash")
        data["channel_name"] = rx.get("channel_name") or rx.get("chan_name")
        data["scope_name"] = scope_name
        data["reply"] = reply

        positions=self.get_companion_positions_by_name(message_data.get('name'))
        position=positions[0] if len(positions)==1 else {}
        data['sender_public_key']=position.get('public_key')
        if data.get('recv_time') is None:data['recv_time']=int(time.time())
        data["sender_latitude"] = position.get("latitude")
        data["sender_longitude"] = position.get("longitude")
        data["sender_altitude"] = position.get("altitude")
        data["sender_position_updated_at"] = position.get("updated_at")

        columns = ", ".join(data)
        placeholders = ", ".join("?" for _ in data)

        cursor = self.db.execute(f"INSERT INTO logger ({columns}) VALUES ({placeholders})", tuple(data.values()))
        self.db.commit()
        return cursor.lastrowid

################################################
# REPEATER FUNCTIONS
################################################

    def get_repeater_count(self):
        row = self.db.execute("SELECT COUNT(*) AS count FROM repeaters").fetchone()
        return row["count"] if row else 0

    def get_repeater_advert_count(self,public_key):
        row = self.db.execute("SELECT advert_count FROM repeaters WHERE public_key = ?", (public_key,)).fetchone()
        return row["advert_count"] if row else 0

    def get_repeaters_by_prefix(self, prefix):
        rows = self.db.execute("SELECT public_key, name, latitude, longitude FROM repeaters WHERE public_key LIKE ?", (prefix.lower() + "%",)).fetchall()
        return [dict(row) for row in rows]

    def get_repeaters_by_name(self, name):
        rows = self.db.execute("SELECT public_key, name FROM repeaters").fetchall()
        wanted_name = name.strip().casefold()
        return [dict(row) for row in rows if (row["name"] or "").strip().casefold() == wanted_name]

    def add_new_repeater(self,event,observed=True):
        from meshcorestation.storage.registry import upsert
        try:return upsert(self.known_path,event.payload or {},observed=observed)
        except (ValueError,TypeError):
            self.logger.warning('Invalid repeater metadata; registry unchanged.')
            return False

################################################
# COMPANION FUNCTIONS
################################################

    def save_companion_position(self, public_key, name, latitude, longitude, altitude, is_bot=False):
        public_key = self._normalize_public_key(public_key)

        if not public_key:
            raise ValueError("Contact has no public key")

        with self.db:
            if is_bot:
                self.db.execute("UPDATE companion_positions SET is_bot = 0 WHERE is_bot = 1 AND public_key != ?", (public_key,))
            self.db.execute("INSERT INTO companion_positions (public_key, name, latitude, longitude, altitude, updated_at, is_bot) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(public_key) DO UPDATE SET name = excluded.name, latitude = excluded.latitude, longitude = excluded.longitude, altitude = excluded.altitude, updated_at = excluded.updated_at, is_bot = MAX(companion_positions.is_bot, excluded.is_bot)", (public_key, name, latitude, longitude, altitude, int(time.time()), int(is_bot)))
    
    def get_companion_position(self, public_key):
        public_key = self._normalize_public_key(public_key)
        row = self.db.execute("SELECT * FROM companion_positions WHERE public_key = ?", (public_key,)).fetchone()
        return dict(row) if row else None

    def get_companion_positions_by_name(self, name):
        rows = self.db.execute("SELECT * FROM companion_positions WHERE is_bot = 0").fetchall()
        wanted_name = (name or "").strip().casefold()
        return [dict(row) for row in rows if wanted_name and row["name"].strip().casefold() == wanted_name]

################################################
# SCOPE FUNCTIONS
################################################

    def add_scope(self, name):
        name = name.strip().removeprefix("#")

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", name):
            raise ValueError("Use 1-30 letters, digits, hyphens or underscores.")

        scope_key = hashlib.sha256(("#" + name).encode("utf-8")).digest()[:16].hex()

        with self.db:
            cursor = self.db.execute("INSERT INTO scopes (name, scope_key) VALUES (?, ?) ON CONFLICT(name) DO NOTHING", (name, scope_key))

        return name, cursor.rowcount == 1

    def get_scopes(self):
        rows = self.db.execute("SELECT name, scope_key FROM scopes ORDER BY name").fetchall()
        return [dict(row) for row in rows]

################################################
# HELPER FUNCTIONS
################################################

    def _normalize_public_key(self, value):
        if value is None:
            return None

        if isinstance(value, bytes):
            return value.hex().lower()

        if isinstance(value, bytearray):
            return bytes(value).hex().lower()

        return str(value).strip().lower()

    def _bytes_to_hex(self, value):
        if value is None:
            return None

        if isinstance(value, bytes):
            return value.hex()

        if isinstance(value, bytearray):
            return bytes(value).hex()

        return str(value)