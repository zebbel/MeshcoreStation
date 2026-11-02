"""The only V5 known-repeater identity store: knownRepeaters.db."""
from pathlib import Path
import math
import re
import sqlite3
import time


def initialize(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not path.exists():path.touch(mode=0o600)
    with sqlite3.connect(path,timeout=5) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS repeaters(
          public_key TEXT PRIMARY KEY CHECK(length(public_key)=64),name TEXT,
          adv_type INTEGER NOT NULL DEFAULT 2,flags INTEGER,latitude REAL,longitude REAL,
          out_path_len INTEGER,out_path TEXT,last_advert INTEGER,lastmod INTEGER,
          first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL DEFAULT 0,
          advert_count INTEGER NOT NULL DEFAULT 0,source TEXT NOT NULL)''')


def key(value):
    value=value.hex() if isinstance(value,(bytes,bytearray)) else str(value or '').strip().lower()
    if not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('A full 64-hex public key is required.')
    return value


def upsert(path,advert,observed=False,now=None):
    if advert.get('type')!=2:return False
    public_key=key(advert.get('public_key'));now=int(time.time() if now is None else now)
    lat,lon=advert.get('adv_lat'),advert.get('adv_lon')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (lat,lon)) or not -90<=lat<=90 or not -180<=lon<=180 or (lat,lon)==(0,0):lat=lon=None
    out=advert.get('out_path');out=out.hex() if isinstance(out,(bytes,bytearray)) else out
    name=advert.get('adv_name') or None
    if name is not None and (not isinstance(name,str) or len(name.encode('utf-8'))>256):raise ValueError('Invalid advertised name.')
    with sqlite3.connect(path,timeout=5) as db:
        db.execute('''INSERT INTO repeaters(public_key,name,adv_type,flags,latitude,longitude,out_path_len,out_path,last_advert,lastmod,first_seen,last_seen,advert_count,source)
          VALUES(?,?,2,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(public_key) DO UPDATE SET
          name=COALESCE(excluded.name,repeaters.name),flags=excluded.flags,
          latitude=COALESCE(excluded.latitude,repeaters.latitude),longitude=COALESCE(excluded.longitude,repeaters.longitude),
          out_path_len=excluded.out_path_len,out_path=excluded.out_path,last_advert=excluded.last_advert,lastmod=excluded.lastmod,
          last_seen=MAX(repeaters.last_seen,excluded.last_seen),advert_count=repeaters.advert_count+excluded.advert_count,
          source=CASE WHEN excluded.advert_count>0 THEN 'advertisement' ELSE repeaters.source END''',
          (public_key,name,advert.get('flags'),lat,lon,advert.get('out_path_len'),out,
           advert.get('last_advert'),advert.get('lastmod'),now,now if observed else 0,int(observed),'advertisement' if observed else 'contact'))
    return True


def observed(path,public_key,count=1):
    public_key=key(public_key)
    with sqlite3.connect(path,timeout=5) as db:
        db.execute("UPDATE repeaters SET last_seen=?,advert_count=advert_count+?,source='advertisement' WHERE public_key=?",(int(time.time()),count,public_key))
