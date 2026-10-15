"""Room persistence and authorization behind an authenticated radio adapter.

This module does not parse radio frames or trust client-supplied author names.
Only an adapter that verifies MeshCore identity and encryption may call post()
or synchronize(). It deliberately has no hooks into the existing channel bot.
"""
from contextlib import contextmanager
from pathlib import Path
import re
import os
import sqlite3
import time


class RoomService:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS identities(
                    room_id INTEGER PRIMARY KEY REFERENCES rooms(id), seed BLOB NOT NULL,
                    public_key TEXT NOT NULL, scope_key TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS sessions_replay(
                    room_id INTEGER NOT NULL REFERENCES rooms(id), public_key TEXT NOT NULL,
                    timestamp INTEGER NOT NULL, PRIMARY KEY(room_id,public_key));
                CREATE TABLE IF NOT EXISTS rooms(
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)));
                CREATE TABLE IF NOT EXISTS members(
                    room_id INTEGER NOT NULL REFERENCES rooms(id), public_key TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('reader','writer','admin')),
                    PRIMARY KEY(room_id,public_key));
                CREATE TABLE IF NOT EXISTS posts(
                    id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL REFERENCES rooms(id),
                    author TEXT NOT NULL, sender_timestamp INTEGER NOT NULL,
                    timestamp INTEGER NOT NULL, text TEXT NOT NULL,
                    UNIQUE(room_id,timestamp), UNIQUE(room_id,author,sender_timestamp));
                CREATE TABLE IF NOT EXISTS replay(
                    room_id INTEGER NOT NULL REFERENCES rooms(id), public_key TEXT NOT NULL,
                    timestamp INTEGER NOT NULL, PRIMARY KEY(room_id,public_key));
                CREATE TABLE IF NOT EXISTS cursors(
                    room_id INTEGER NOT NULL REFERENCES rooms(id), public_key TEXT NOT NULL,
                    timestamp INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(room_id,public_key));
            ''')

        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def public_key(value):
        if not isinstance(value,str) or not re.fullmatch('[0-9a-fA-F]{64}',value):
            raise ValueError('A full public key is required.')
        return value.lower()

    @staticmethod
    def timestamp(value):
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('Invalid protocol timestamp.')
        return value

    def create(self, name):
        if not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>31 or any(ord(c)<32 for c in name):
            raise ValueError('Room names must contain 1–31 UTF-8 bytes without control characters.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM rooms').fetchone()[0] >= 4:
                raise ValueError('At most four rooms can share the radio.')
            from .wire import Identity
            identity = Identity.generate()
            room = db.execute('INSERT INTO rooms(name) VALUES(?)',(name.strip(),)).lastrowid
            db.execute('INSERT INTO identities(room_id,seed,public_key) VALUES(?,?,?)',
                       (room,identity.seed,identity.public.hex()))
            return room

    def rooms(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,name,enabled FROM rooms ORDER BY id')]

    def set_enabled(self, room, enabled):
        if type(enabled) is not bool:
            raise ValueError('Enabled must be a boolean.')
        with self.connect() as db:
            if db.execute('UPDATE rooms SET enabled=? WHERE id=?',(int(enabled),room)).rowcount!=1:
                raise ValueError('Unknown room.')

    def grant(self, room, key, role):
        """Local administrative operation, never directly exposed to RF callers."""
        key=self.public_key(key)
        if role not in ('reader','writer','admin'):
            raise ValueError('Unknown permission.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM members WHERE room_id=? AND public_key=?',(room,key)).fetchone() and db.execute('SELECT COUNT(*) FROM members WHERE room_id=?',(room,)).fetchone()[0]>=64:
                raise ValueError('At most 64 members per room.')
            db.execute('INSERT INTO members VALUES(?,?,?) ON CONFLICT(room_id,public_key) DO UPDATE SET role=excluded.role',(room,key,role))

    def revoke(self, room, key):
        key=self.public_key(key)
        with self.connect() as db:
            db.execute('DELETE FROM members WHERE room_id=? AND public_key=?',(room,key))
            db.execute('DELETE FROM cursors WHERE room_id=? AND public_key=?',(room,key))
            # Retain replay protection across revocation and subsequent reapproval.

    @staticmethod
    def authorize(db, room, key, write=False):
        row=db.execute('SELECT m.role FROM members m JOIN rooms r ON r.id=m.room_id WHERE r.id=? AND m.public_key=? AND r.enabled=1',(room,key)).fetchone()
        if row is None or (write and row['role']=='reader'):
            raise PermissionError('Room access denied or room disabled.')

    def post(self, room, authenticated_key, sender_timestamp, text):
        key=self.public_key(authenticated_key)
        stamp=self.timestamp(sender_timestamp)
        if not isinstance(text,str) or not text or len(text.encode('utf-8'))>151 or any(ord(c)<32 or ord(c)==127 for c in text):
            raise ValueError('Posts must contain 1–151 UTF-8 bytes without control characters.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.authorize(db,room,key,write=True)
            existing=db.execute('SELECT * FROM posts WHERE room_id=? AND author=? AND sender_timestamp=?',(room,key,stamp)).fetchone()
            if existing:
                if existing['text']!=text:
                    raise ValueError('Conflicting replay.')
                return dict(existing)
            last=db.execute('SELECT timestamp FROM replay WHERE room_id=? AND public_key=?',(room,key)).fetchone()
            if last and stamp<=last[0]:
                raise ValueError('Stale sender timestamp.')
            previous=db.execute('SELECT MAX(timestamp) FROM posts WHERE room_id=?',(room,)).fetchone()[0]
            now=self.timestamp(max(int(self.clock()),(previous+1) if previous is not None else 0))
            cursor=db.execute('INSERT INTO posts(room_id,author,sender_timestamp,timestamp,text) VALUES(?,?,?,?,?)',(room,key,stamp,now,text))
            db.execute('INSERT INTO replay VALUES(?,?,?) ON CONFLICT(room_id,public_key) DO UPDATE SET timestamp=excluded.timestamp',(room,key,stamp))
            return dict(db.execute('SELECT * FROM posts WHERE id=?',(cursor.lastrowid,)).fetchone())

    def synchronize(self, room, authenticated_key, since, limit=20):
        key=self.public_key(authenticated_key)
        since=self.timestamp(since)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Invalid batch limit.')
        with self.connect() as db:
            self.authorize(db,room,key)
            # MeshCore rooms do not push an author's own posts back to them.
            return [dict(row) for row in db.execute('SELECT * FROM posts WHERE room_id=? AND timestamp>? AND author!=? ORDER BY timestamp LIMIT ?',(room,since,key,limit))]

    def acknowledge(self, room, authenticated_key, post_timestamp):
        """Call only after the radio adapter verifies a pending push ACK."""
        key=self.public_key(authenticated_key)
        stamp=self.timestamp(post_timestamp)
        with self.connect() as db:
            self.authorize(db,room,key)
            if not db.execute('SELECT 1 FROM posts WHERE room_id=? AND timestamp=? AND author!=?',(room,stamp,key)).fetchone():
                raise ValueError('Unknown delivered post.')
            db.execute('INSERT INTO cursors VALUES(?,?,?) ON CONFLICT(room_id,public_key) DO UPDATE SET timestamp=MAX(timestamp,excluded.timestamp)',(room,key,stamp))

    def config(self, room):
        with self.connect() as db:
            row = db.execute('SELECT r.*,i.public_key,i.scope_key FROM rooms r JOIN identities i ON r.id=i.room_id WHERE r.id=?',(room,)).fetchone()
            if row is None:
                raise ValueError('Unknown room.')
            return dict(row)

    def details(self, room):
        with self.connect() as db:
            row = db.execute('SELECT r.*,i.public_key,i.scope_key FROM rooms r JOIN identities i ON r.id=i.room_id WHERE r.id=?',(room,)).fetchone()
            if row is None:
                raise ValueError('Unknown room.')
            result = dict(row)
            result['members'] = [dict(r) for r in db.execute('SELECT public_key,role FROM members WHERE room_id=? ORDER BY public_key',(room,))]
            result['posts'] = [dict(r) for r in db.execute('SELECT * FROM (SELECT * FROM posts WHERE room_id=? ORDER BY timestamp DESC LIMIT 100) ORDER BY timestamp',(room,))]
            return result

    def identity(self, room):
        from .wire import Identity
        with self.connect() as db:
            row = db.execute('SELECT seed FROM identities WHERE room_id=?',(room,)).fetchone()
            if row is None:
                raise ValueError('Room has no identity; create a new room.')
            return Identity(bytes(row[0]))

    def configure_scope(self, room, value):
        if not isinstance(value,str) or (value and not re.fullmatch('[0-9a-fA-F]{32}',value)):
            raise ValueError('Scope key must be empty (unscoped) or 32 hexadecimal characters.')
        with self.connect() as db:
            if not db.execute('UPDATE identities SET scope_key=? WHERE room_id=?',(value.lower(),room)).rowcount:
                raise ValueError('Unknown room.')

    def access(self, room, key):
        with self.connect() as db:
            self.authorize(db,room,key)
            return db.execute('SELECT role FROM members WHERE room_id=? AND public_key=?',(room,key)).fetchone()[0]

    def accept_timestamp(self, room, key, stamp, login=False):
        """Persist control/login replay protection, independently of post deduplication."""
        stamp = self.timestamp(stamp)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.authorize(db,room,key)
            row = db.execute('SELECT timestamp FROM sessions_replay WHERE room_id=? AND public_key=?',(room,key)).fetchone()
            if row and (stamp < row[0] or (login and stamp == row[0])):
                raise ValueError('Stale sender timestamp.')
            db.execute('INSERT INTO sessions_replay VALUES(?,?,?) ON CONFLICT(room_id,public_key) DO UPDATE SET timestamp=excluded.timestamp',(room,key,stamp))

    def local_post(self, room, text):
        identity = self.identity(room)
        key = identity.public.hex()
        self.grant(room,key,'admin')
        with self.connect() as db:
            previous = db.execute('SELECT MAX(sender_timestamp) FROM posts WHERE room_id=? AND author=?',(room,key)).fetchone()[0]
        return self.post(room,key,max(int(self.clock()),(previous or 0)+1),text)
