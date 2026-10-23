"""Authenticated command reception evidence, separate from command execution."""
import hashlib
import hmac
import json
import math
import time
from Crypto.Cipher import AES


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS command_rx_bindings (
            identity TEXT PRIMARY KEY,
            command_id INTEGER NOT NULL UNIQUE REFERENCES logger(id) ON DELETE CASCADE,
            scope TEXT);
        CREATE TABLE IF NOT EXISTS command_receptions (
            id INTEGER PRIMARY KEY, identity TEXT NOT NULL, scope TEXT NOT NULL,
            path TEXT, path_len INTEGER, path_hash_size INTEGER, route_type INTEGER,
            rssi REAL, snr REAL, received_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS command_rx_identity ON command_receptions(identity,id);
    ''')


def channel_identity(key, stamp, text):
    if not isinstance(key, bytes) or stamp is None:
        return None
    return hashlib.sha256(json.dumps(['channel', hashlib.sha256(key).hexdigest(), stamp, text],
                                    separators=(',', ':')).encode()).hexdigest()


def room_identity(room, post):
    return hashlib.sha256(json.dumps(['room', room, post['author'], post.get('sender_timestamp'), post['text']], separators=(',', ':')).encode()).hexdigest()


def authenticate(rx, key, scopes=()):
    """Do not trust channel-name/one-byte-key-hash matches for history binding."""
    payload = rx.get('pkt_payload')
    if not isinstance(payload, bytes) or len(payload) < 19 or (len(payload)-3) % 16:
        return None
    if payload[0] != hashlib.sha256(key).digest()[0]:
        return None
    if not hmac.compare_digest(payload[1:3], hmac.new(key, payload[3:], hashlib.sha256).digest()[:2]):
        return None
    clear = AES.new(key, AES.MODE_ECB).decrypt(payload[3:])
    if clear[4] >> 2:
        return None
    try:
        text = clear[5:].rstrip(b'\0').decode('utf-8')
    except UnicodeDecodeError:
        return None
    scope = 'unscoped'
    if rx.get('route_type') in (0, 3):
        try:
            code = bytes.fromhex(rx['transport_code'])
            if len(code) != 4:
                return None
            received = int.from_bytes(code[:2], 'little')
            matches = set()
            for entry in scopes:
                secret = bytes.fromhex(entry['scope_key'])
                digest = hmac.new(secret, b'\x05'+payload, hashlib.sha256).digest()
                value = int.from_bytes(digest[:2], 'little')
                value = 1 if value == 0 else 65534 if value == 65535 else value
                if received == value:
                    matches.add(hashlib.sha256(secret).hexdigest())
            if len(matches) != 1:
                return None
            scope = matches.pop()
        except (KeyError, ValueError, TypeError):
            return None
    return channel_identity(key, int.from_bytes(clear[:4], 'little'), text), scope, text


def existing(db, identity):
    if not identity:
        return None
    row = db.execute('SELECT command_id FROM command_rx_bindings WHERE identity=?', (identity,)).fetchone()
    return row[0] if row else None


def bind(db, identity, command_id, scope=None):
    if not identity:
        return
    if scope is None:
        scopes = db.execute('SELECT DISTINCT scope FROM command_receptions WHERE identity=?', (identity,)).fetchall()
        scope = scopes[0][0] if len(scopes) == 1 else None
    with db:
        db.execute('INSERT INTO command_rx_bindings VALUES (?,?,?)', (identity, command_id, scope))


def record(db, identity, rx, scope='unscoped', now=None):
    if not identity:
        return
    now = time.time() if now is None else now
    path = rx.get('path')
    if isinstance(path, (bytes, bytearray)):
        path = path.hex()
    elif path is not None:
        path = str(path).lower()
    def number(name):
        value = rx.get(name)
        return value if type(value) in (int, float) and math.isfinite(value) else None
    with db:
        db.execute('''INSERT INTO command_receptions
            (identity,scope,path,path_len,path_hash_size,route_type,rssi,snr,received_at)
            VALUES (?,?,?,?,?,?,?,?,?)''', (identity, scope, path, number('path_len'),
            number('path_hash_size'), number('route_type'), number('rssi'), number('snr'), now))


def paths(db, command_id):
    """Group by route; retain every reception's metrics/time in observations."""
    rows = db.execute('''SELECT r.* FROM command_receptions r JOIN command_rx_bindings b
        ON b.identity=r.identity AND (b.scope IS NULL OR b.scope=r.scope)
        WHERE b.command_id=? ORDER BY r.id''', (command_id,)).fetchall()
    # An unscoped callback cannot disambiguate identical text/timestamps from
    # different scopes. Do not guess which of those observations belongs to it.
    if len({r['scope'] for r in rows}) > 1:
        return []
    grouped = {}
    for row in rows:
        key = tuple(row[k] for k in ('path', 'path_len', 'path_hash_size', 'route_type'))
        if key not in grouped:
            grouped[key] = dict(id=row['id'], rx_path=row['path'], path_len=row['path_len'],
                                path_hash_size=row['path_hash_size'], route_type=row['route_type'],
                                rssi=row['rssi'], snr=row['snr'], recv_time=row['received_at'], observations=[])
        grouped[key]['observations'].append(dict(rssi=row['rssi'], snr=row['snr'], recv_time=row['received_at']))
    return list(grouped.values())
