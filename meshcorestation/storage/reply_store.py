"""Passive evidence for outgoing command replies; never treats silence as failure."""
import hashlib
import hmac
import json
import math
import time
from Crypto.Cipher import AES
from meshcorestation.storage.passive_stats import normalize

WINDOW = 300


def initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS command_replies (
          id INTEGER PRIMARY KEY, command_id INTEGER NOT NULL REFERENCES logger(id) ON DELETE CASCADE,
          created_at REAL NOT NULL, timestamp INTEGER NOT NULL, channel_key_hash TEXT NOT NULL,
          raw_text TEXT NOT NULL, message TEXT NOT NULL, scope TEXT NOT NULL,
          scope_key_hash TEXT, send_status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS reply_command ON command_replies(command_id,id);
        CREATE INDEX IF NOT EXISTS reply_created ON command_replies(created_at);
        CREATE TABLE IF NOT EXISTS reply_observations (
          id INTEGER PRIMARY KEY, reply_id INTEGER NOT NULL REFERENCES command_replies(id) ON DELETE CASCADE,
          seen_at REAL NOT NULL, latency REAL NOT NULL, digest TEXT NOT NULL, path TEXT NOT NULL,
          route TEXT NOT NULL, rssi REAL, snr REAL,
          UNIQUE(reply_id,digest,path));
    """)

    columns={r[1] for r in db.execute('PRAGMA table_info(command_replies)')}
    for name,definition in {'parent_reply_id':'INTEGER','attempt_no':'INTEGER NOT NULL DEFAULT 1',
          'hop_count':'INTEGER','max_attempts':'INTEGER NOT NULL DEFAULT 1',
          'retry_status':"TEXT NOT NULL DEFAULT 'legacy'",'retry_detail':"TEXT NOT NULL DEFAULT ''",
          'next_retry_at':'REAL'}.items():
        if name not in columns:db.execute('ALTER TABLE command_replies ADD COLUMN '+name+' '+definition)
    db.execute('CREATE INDEX IF NOT EXISTS reply_parent ON command_replies(parent_reply_id)')


def retry_plan(db,root,hops,maximum):
    with db:db.execute('UPDATE command_replies SET hop_count=?,max_attempts=? WHERE id=?',(hops,maximum,root))


def retry_state(db,root,status,detail='',next_at=None):
    with db:db.execute('UPDATE command_replies SET retry_status=?,retry_detail=?,next_retry_at=? WHERE id=?',
                       (status,str(detail)[:300],next_at,root))


def interrupt_pending(db):
    with db:db.execute("UPDATE command_replies SET retry_status='cancelled',retry_detail='Station restarted; pending retries were not resumed.',next_retry_at=NULL WHERE retry_status='pending'")


def root_id(db,reply_id):
    row=db.execute('SELECT parent_reply_id FROM command_replies WHERE id=?',(reply_id,)).fetchone()
    return (row[0] or reply_id) if row else None


def has_forwarding(db,root):
    return db.execute("""SELECT 1 FROM reply_observations o JOIN command_replies r ON r.id=o.reply_id
                         WHERE r.id=? OR r.parent_reply_id=? LIMIT 1""",(root,root)).fetchone() is not None


def begin(db, command_id, message, name, key, stamp, scope, scope_key, now=None, parent=None, attempt=1):
    now = time.time() if now is None else now
    with db:
        cursor = db.execute("""INSERT INTO command_replies
            (command_id,created_at,timestamp,channel_key_hash,raw_text,message,scope,scope_key_hash,send_status,parent_reply_id,attempt_no)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (command_id,now,stamp,hashlib.sha256(key).hexdigest(),f'{name}: {message}',
             message,scope,hashlib.sha256(scope_key).hexdigest() if scope_key else None,'submitting',parent,attempt))
    return cursor.lastrowid


def finish(db, reply_id, status, detail=''):
    with db:
        db.execute('UPDATE command_replies SET send_status=?,detail=? WHERE id=?',(status,str(detail)[:300],reply_id))


def observe(db, rx, key, scopes, now=None):
    now = time.time() if now is None else now
    packet = normalize(rx)
    if not packet or packet['kind'] != 5 or not packet['path'] or rx.get('route_type') not in (0,1):
        return
    payload = rx.get('pkt_payload')
    if not isinstance(payload,bytes) or len(payload)<19 or (len(payload)-3)%16:
        return
    # Verify with the configured channel key ourselves, rather than relying on
    # the parser's short-hash cache or potentially colliding channel names.
    if payload[0] != hashlib.sha256(key).digest()[0]:
        return
    cipher = payload[3:]
    if not hmac.compare_digest(payload[1:3],hmac.new(key,cipher,hashlib.sha256).digest()[:2]):
        return
    clear = AES.new(key,AES.MODE_ECB).decrypt(cipher)
    stamp = int.from_bytes(clear[:4],'little')
    if clear[4] >> 2 != 0:
        return
    try:
        text = clear[5:].rstrip(b'\0').decode('utf-8')
    except UnicodeDecodeError:
        return
    scope_hash = None
    if rx['route_type']==0:
        try:
            code = bytes.fromhex(rx['transport_code'])
            if len(code)!=4:return
            received = int.from_bytes(code[:2],'little')
            matches = set()
            for scope in scopes:
                secret = bytes.fromhex(scope['scope_key'])
                digest = hmac.new(secret,b'\x05'+payload,hashlib.sha256).digest()
                value = int.from_bytes(digest[:2],'little')
                value = 1 if value==0 else 65534 if value==65535 else value
                if value==received:
                    matches.add(hashlib.sha256(secret).hexdigest())
            if len(matches)!=1:return
            scope_hash = matches.pop()
        except (KeyError,ValueError,TypeError):
            return
    candidates = db.execute("""SELECT * FROM command_replies WHERE
        created_at>=? AND created_at<=? AND timestamp=? AND channel_key_hash=? AND raw_text=?
        AND scope_key_hash IS ? AND send_status IN ('submitting','accepted','uncertain')""",
        (now-WINDOW,now,stamp,hashlib.sha256(key).hexdigest(),text,scope_hash)).fetchall()
    # Identical submissions within one second are not distinguishable on air.
    if len(candidates)!=1:
        return
    reply = candidates[0]
    if db.execute('SELECT count(*) FROM reply_observations WHERE reply_id=?',(reply['id'],)).fetchone()[0]>=64:
        return
    repeaters = db.execute('SELECT public_key,name FROM repeaters').fetchall()
    route = []
    for prefix in packet['path']:
        matches = [r for r in repeaters if r['public_key'].lower().startswith(prefix)]
        route.append(dict(prefix=prefix, name=matches[0]['name'] if len(matches)==1 else prefix,
                          public_key=matches[0]['public_key'] if len(matches)==1 else None,
                          status='forwarding observed' if len(matches)==1 else 'ambiguous repeater' if matches else 'unknown repeater'))
    path = json.dumps(packet['path'])
    def number(name):
        value = rx.get(name)
        return value if type(value) in (int,float) and math.isfinite(value) else None
    with db:
        db.execute("""INSERT OR IGNORE INTO reply_observations
            (reply_id,seen_at,latency,digest,path,route,rssi,snr) VALUES (?,?,?,?,?,?,?,?)""",
            (reply['id'],now,max(0,now-reply['created_at']),packet['digest'],path,json.dumps(route),number('rssi'),number('snr')))

    return reply['id']


def snapshot(db, command_id):
    rows=db.execute('SELECT * FROM command_replies WHERE command_id=? AND parent_reply_id IS NULL ORDER BY id LIMIT 100',(command_id,)).fetchall()
    def entry(row):
        observations=[dict(o) for o in db.execute('SELECT seen_at,latency,route,rssi,snr FROM reply_observations WHERE reply_id=? ORDER BY seen_at,id',(row['id'],))]
        for o in observations:o['route']=json.loads(o['route'])
        return dict(id=row['id'],message=row['message'],created_at=row['created_at'],timestamp=row['timestamp'],
                    attempt=row['attempt_no'],scope=row['scope'],send_status=row['send_status'],detail=row['detail'],observations=observations)
    result=[]
    for row in rows:
        item=entry(row)
        item.update(hop_count=row['hop_count'],max_attempts=row['max_attempts'],retry_status=row['retry_status'],
                    retry_detail=row['retry_detail'],next_retry_at=row['next_retry_at'])
        item['attempts']=[entry(row)]+[entry(a) for a in db.execute('SELECT * FROM command_replies WHERE parent_reply_id=? ORDER BY attempt_no,id LIMIT 3',(row['id'],))]
        result.append(item)
    return dict(replies=result,window_seconds=WINDOW)
