"""Room persistence and authorization behind an authenticated radio adapter.

This module does not parse radio frames or trust client-supplied author names.
Only an adapter that verifies MeshCore identity and encryption may call post()
or synchronize(). A room can optionally be selected as the station bot transport;
that selection is local state and does not grant radio administration.
"""
from contextlib import contextmanager
from pathlib import Path
import re
import hashlib
import hmac
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
                CREATE TABLE IF NOT EXISTS room_auth(
                    room_id INTEGER PRIMARY KEY REFERENCES rooms(id),
                    salt BLOB NOT NULL, password_hash BLOB NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS identities(
                    room_id INTEGER PRIMARY KEY REFERENCES rooms(id), seed BLOB NOT NULL,
                    public_key TEXT NOT NULL, scope_key TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS sessions_replay(
                    room_id INTEGER NOT NULL REFERENCES rooms(id), public_key TEXT NOT NULL,
                    timestamp INTEGER NOT NULL, PRIMARY KEY(room_id,public_key));
                CREATE TABLE IF NOT EXISTS rooms(
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
                    is_bot INTEGER NOT NULL DEFAULT 0 CHECK(is_bot IN (0,1)));
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
            columns = {row['name'] for row in db.execute('PRAGMA table_info(rooms)')}
            if 'is_bot' not in columns:
                db.execute('ALTER TABLE rooms ADD COLUMN is_bot INTEGER NOT NULL DEFAULT 0 CHECK(is_bot IN (0,1))')
            # Never turn an existing private ACL room into an open/passwordless room.
            db.execute('UPDATE rooms SET enabled=0 WHERE id NOT IN (SELECT room_id FROM room_auth)')

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
            return [dict(row) for row in db.execute('SELECT id,name,enabled,is_bot FROM rooms ORDER BY id')]

    def set_enabled(self, room, enabled):
        if type(enabled) is not bool:
            raise ValueError('Enabled must be a boolean.')
        with self.connect() as db:
            if enabled and not db.execute('SELECT 1 FROM room_auth WHERE room_id=?',(room,)).fetchone():
                raise ValueError('Set a room password before enabling it.')
            if db.execute('UPDATE rooms SET enabled=? WHERE id=?',(int(enabled),room)).rowcount!=1:
                raise ValueError('Unknown room.')

    def set_bot(self, room):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM rooms WHERE id=?',(room,)).fetchone():
                raise ValueError('Unknown room.')
            db.execute('UPDATE rooms SET is_bot=0 WHERE is_bot=1')
            db.execute('UPDATE rooms SET is_bot=1 WHERE id=?',(room,))

    def clear_bot(self):
        with self.connect() as db:
            db.execute('UPDATE rooms SET is_bot=0 WHERE is_bot=1')

    def bot_room(self):
        with self.connect() as db:
            row = db.execute('SELECT id FROM rooms WHERE is_bot=1 ORDER BY id LIMIT 1').fetchone()
            return row[0] if row else None

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

    def post(self, room, authenticated_key, sender_timestamp, text, return_created=False):
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
                result = dict(existing)
                return (result, False) if return_created else result
            last=db.execute('SELECT timestamp FROM replay WHERE room_id=? AND public_key=?',(room,key)).fetchone()
            if last and stamp<=last[0]:
                raise ValueError('Stale sender timestamp.')
            previous=db.execute('SELECT MAX(timestamp) FROM posts WHERE room_id=?',(room,)).fetchone()[0]
            now=self.timestamp(max(int(self.clock()),(previous+1) if previous is not None else 0))
            cursor=db.execute('INSERT INTO posts(room_id,author,sender_timestamp,timestamp,text) VALUES(?,?,?,?,?)',(room,key,stamp,now,text))
            db.execute('INSERT INTO replay VALUES(?,?,?) ON CONFLICT(room_id,public_key) DO UPDATE SET timestamp=excluded.timestamp',(room,key,stamp))
            result = dict(db.execute('SELECT * FROM posts WHERE id=?',(cursor.lastrowid,)).fetchone())
            return (result, True) if return_created else result

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
            row = db.execute('SELECT r.*,i.public_key,COALESCE(a.revision,0) AS auth_revision FROM rooms r JOIN identities i ON r.id=i.room_id LEFT JOIN room_auth a ON a.room_id=r.id WHERE r.id=?',(room,)).fetchone()
            if row is None:
                raise ValueError('Unknown room.')
            return dict(row)

    def details(self, room):
        with self.connect() as db:
            row = db.execute('SELECT r.*,i.public_key,COALESCE(a.revision,0) AS auth_revision FROM rooms r JOIN identities i ON r.id=i.room_id LEFT JOIN room_auth a ON a.room_id=r.id WHERE r.id=?',(room,)).fetchone()
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

    def set_password(self, room, password):
        if not isinstance(password,str) or not 1 <= len(password.encode('utf-8')) <= 15 or any(ord(c)<32 or ord(c)==127 for c in password):
            raise ValueError('Password must contain 1–15 UTF-8 bytes without control characters.')
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,100000)
        with self.connect() as db:
            db.execute('INSERT INTO room_auth VALUES(?,?,?,1) ON CONFLICT(room_id) DO UPDATE SET salt=excluded.salt,password_hash=excluded.password_hash,revision=revision+1',(room,salt,digest))

    def login(self, room, key, timestamp, password):
        """Called only after decrypting/authenticating the sender's anonymous packet."""
        key = self.public_key(key)
        timestamp = self.timestamp(timestamp)
        if not isinstance(password,bytes) or not 1 <= len(password) <= 15:
            raise PermissionError('Incorrect room password.')
        with self.connect() as db:
            auth = db.execute('SELECT a.* FROM room_auth a JOIN rooms r ON r.id=a.room_id WHERE r.id=? AND r.enabled=1',(room,)).fetchone()
        if auth is None:
            raise PermissionError('Room disabled or password not set.')
        digest = hashlib.pbkdf2_hmac('sha256',password,auth['salt'],100000)
        if not hmac.compare_digest(digest,auth['password_hash']):
            raise PermissionError('Incorrect room password.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT a.revision FROM room_auth a JOIN rooms r ON r.id=a.room_id WHERE r.id=? AND r.enabled=1',(room,)).fetchone()
            if current is None or current[0] != auth['revision']:
                raise PermissionError('Password changed; log in again.')
            last = db.execute('SELECT timestamp FROM sessions_replay WHERE room_id=? AND public_key=?',(room,key)).fetchone()
            if last and timestamp <= last[0]:
                raise ValueError('Stale sender timestamp.')
            member = db.execute('SELECT role FROM members WHERE room_id=? AND public_key=?',(room,key)).fetchone()
            if member is None:
                if db.execute('SELECT COUNT(*) FROM members WHERE room_id=?',(room,)).fetchone()[0] >= 64:
                    raise PermissionError('Room participant limit reached.')
                db.execute("INSERT INTO members VALUES(?,?,'writer')",(room,key))
            db.execute('INSERT INTO sessions_replay VALUES(?,?,?) ON CONFLICT(room_id,public_key) DO UPDATE SET timestamp=excluded.timestamp',(room,key,timestamp))
            return (member[0] if member else 'writer'), auth['revision']

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
