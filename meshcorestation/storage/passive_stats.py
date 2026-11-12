"""V5 passive evidence, adapted from V4's collision-aware route attribution.

Only the worker writes per-managed-repeater stores. No subscriptions, RF requests,
network-wide database, deduplication or automatic retention/deletion.
"""
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
import time
import uuid

from meshcorestation.storage.connection import connect as open_database
from meshcorestation.storage.voltage_store import MEMBERSHIP_LOCK
from meshcorestation.storage.statistics_classification import SOURCE_SCHEMA

MIN_FREE_BYTES = 64 * 1024 * 1024
SCHEMA = '''
CREATE TABLE IF NOT EXISTS observations(
 id INTEGER PRIMARY KEY, reception_id TEXT NOT NULL UNIQUE, received_at REAL NOT NULL,
 recorded_at REAL NOT NULL, packet_type INTEGER NOT NULL, route_type INTEGER NOT NULL,
 scoped INTEGER NOT NULL, transport_code TEXT, payload BLOB, raw_packet BLOB,
 packet_digest TEXT, client_digest TEXT, metadata TEXT NOT NULL,
 rssi REAL, snr REAL, hop_count INTEGER NOT NULL, path_hash_size INTEGER NOT NULL,
 path_raw BLOB NOT NULL, route TEXT NOT NULL, positions TEXT NOT NULL,
 first_hop INTEGER NOT NULL, middle_hop INTEGER NOT NULL, last_hop INTEGER NOT NULL,
 previous TEXT NOT NULL, following TEXT NOT NULL, confidence TEXT NOT NULL,
 ambiguous INTEGER NOT NULL, evidence TEXT NOT NULL, registry_checked_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS observations_timestamp ON observations(received_at,id);
CREATE INDEX IF NOT EXISTS observations_digest ON observations(packet_digest);
CREATE TABLE IF NOT EXISTS collection_health(
 id INTEGER PRIMARY KEY CHECK(id=1), observation_count INTEGER NOT NULL DEFAULT 0,
 last_recorded_at REAL, last_received_at REAL);
INSERT OR IGNORE INTO collection_health(id) VALUES(1);
'''


def _bytes(value):
    if isinstance(value, (bytes, bytearray)): return bytes(value)
    if isinstance(value, str): return bytes.fromhex(value)
    raise ValueError('Missing packet bytes.')


def _metadata(value, depth=0):
    # Preserve decoded evidence, never persist client channel secrets/passwords.
    if depth > 8: raise ValueError('Packet metadata is too deeply nested.')
    if isinstance(value, (bytes, bytearray)): return {'hex': bytes(value).hex()}
    if isinstance(value, dict):
        return {str(k): _metadata(v, depth+1) for k,v in value.items()
                if not any(word in str(k).lower() for word in ('secret', 'password', 'private_key'))}
    if isinstance(value, (list, tuple)): return [_metadata(v, depth+1) for v in value]
    if value is None or type(value) in (str, int, bool): return value
    if type(value) is float and math.isfinite(value): return value
    return None


def normalize(rx, now_ns=None):
    """Snapshot the client event before bot/channel filters; preserve every copy.

    Flood paths are observed route evidence. Direct paths are routing instructions,
    and TRACE paths may use mixed encoding: neither confirms forwarding positions.
    """
    try:
        if not isinstance(rx, dict): return None
        kind, route_type = rx['payload_type'], rx['route_type']
        size, count = rx['path_hash_size'], rx['path_len']
        if any(type(v) is not int for v in (kind, route_type, size, count)): return None
        if not (0 <= kind <= 15 and 0 <= route_type <= 3 and 1 <= size <= 4 and 0 <= count <= 63): return None
        path = _bytes(rx['path'])
        if len(path) != size * count or len(path) > 252: return None
        payload = _bytes(rx['pkt_payload']) if rx.get('pkt_payload') is not None else None
        raw = _bytes(rx['payload']) if rx.get('payload') is not None else None
        if any(v is not None and len(v) > 1024 for v in (payload, raw)): return None
        metadata = json.dumps(_metadata(rx), ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        if len(metadata.encode('utf-8')) > 32768: return None
        def number(name):
            v = rx.get(name)
            return v if type(v) in (int, float) and math.isfinite(v) else None
        stamp = time.time_ns() if now_ns is None else now_ns
        return dict(reception_id=uuid.uuid4().hex, received_ns=stamp, received_at=stamp/1e9,
                    kind=kind, route_type=route_type, size=size, count=count, path_raw=path,
                    path=[path[i:i+size].hex() for i in range(0,len(path),size)],
                    payload=payload, raw=raw, metadata=metadata, rssi=number('rssi'), snr=number('snr'),
                    transport_code=rx.get('transport_code') if isinstance(rx.get('transport_code'), str) else None,
                    digest=hashlib.sha256(bytes([kind])+payload).hexdigest() if payload is not None else None,
                    client_digest=str(rx['pkt_hash']) if isinstance(rx.get('pkt_hash'), (str,int)) else None,
                    advert_key=(payload[:32].hex() if kind==4 and payload is not None and len(payload)>=101
                                and payload[100]&15==2 else None))
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def attribute(packet, keys, managed):
    """Match against *all* canonical identities; only yield managed candidates.

    Like V4, ambiguous hash matches are saved for each candidate with explicit
    uncertainty. No name or full key is assigned to an ambiguous route segment.
    """
    prefixes = {}
    for key in keys:
        prefix = key[:packet['size']*2]
        prefixes.setdefault(prefix, []).append(key)
    route = []
    targets = set()
    for prefix in packet['path']:
        matches = prefixes.get(prefix, [])
        targets.update(set(matches) & managed)
        route.append(dict(hash=prefix, candidates=matches, public_key=matches[0] if len(matches)==1 and packet['kind']!=9 else None,
                          status='uninterpreted' if packet['kind']==9 else 'matched' if len(matches)==1 else 'ambiguous' if matches else 'unknown'))
    advert = packet['advert_key']
    if advert in managed: targets.add(advert)
    observed_route = packet['route_type'] in (0,1) and packet['kind'] != 9
    for key in targets:
        indices = [i for i,hop in enumerate(route) if key in hop['candidates']]
        confirmed = [i for i in indices if route[i]['status']=='matched'] if observed_route else []
        ambiguous = any(route[i]['status']!='matched' for i in indices) or (bool(indices) and not observed_route)
        # Complete payload key identifies an advert origin, not a forwarding hop.
        evidence = 'advertisement-origin' if advert==key else 'observed-flood-route' if observed_route else 'uninterpreted-trace-route' if packet['kind']==9 else 'direct-routing-path'
        positions = [dict(index=i, first=i==0, middle=0<i<len(route)-1, last=i==len(route)-1,
                          confidence='unambiguous-hash' if i in confirmed else 'ambiguous') for i in indices] if observed_route else []
        yield key, dict(route=route, positions=positions,
            first_hop=int(0 in confirmed), middle_hop=int(any(0<i<len(route)-1 for i in confirmed)),
            last_hop=int(len(route)-1 in confirmed),
            previous=[route[i-1] for i in indices if i>0] if observed_route else [],
            following=[route[i+1] for i in indices if i+1<len(route)] if observed_route else [],
            confidence='ambiguous' if ambiguous else 'full-key-origin' if advert==key else 'unambiguous-hash',
            ambiguous=int(ambiguous), evidence=evidence)


def statistics_path(main_path, key):
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('A complete repeater public key is required.')
    return Path(main_path).parent / 'repeaterStatistics' / (key+'.db')


def _write(path, rows):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists(): path.touch(mode=0o600)
    with closing(sqlite3.connect(path, timeout=0.25)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript(SCHEMA)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='classification_source'").fetchone():
            db.executescript("BEGIN IMMEDIATE;"+SOURCE_SCHEMA+"COMMIT;")
        with db:
            db.executemany('''INSERT INTO observations(reception_id,received_at,recorded_at,packet_type,route_type,
                scoped,transport_code,payload,raw_packet,packet_digest,client_digest,metadata,rssi,snr,hop_count,
                path_hash_size,path_raw,route,positions,first_hop,middle_hop,last_hop,previous,following,
                confidence,ambiguous,evidence,registry_checked_at) VALUES('''+','.join('?'*28)+')', rows)
            db.execute('''UPDATE collection_health SET observation_count=observation_count+?,
                last_recorded_at=?,last_received_at=MAX(COALESCE(last_received_at,0),?) WHERE id=1''',
                (len(rows), time.time(), max(row[1] for row in rows)))


def store_batch(main_path, batch):
    """Off-loop batched writer. The mutex serializes managed-list changes only.

    Main DB is read-only: do not hold a main write lock that could stall radio
    history writes. API removal uses the same mutex until membership is committed.
    Re-add cutoff rejects observations queued before the new membership began.
    """
    results, errors = {}, {}
    with MEMBERSHIP_LOCK, closing(open_database(Path(main_path).as_uri()+'?mode=ro', timeout=0.25)) as db:
        db.execute('BEGIN')
        managed = {r['public_key']: r['statistics_since_ns'] for r in db.execute(
            "SELECT public_key,statistics_since_ns FROM voltage_config WHERE managed=1 AND public_key!=''")}
        if not managed or not batch: return results, errors
        keys = {r[0] for r in db.execute('SELECT public_key FROM repeaters')}
        grouped = {}
        now = time.time()
        for packet in batch:
            for key, attribution in attribute(packet, keys, set(managed)):
                if packet['received_ns'] < managed[key]: continue
                j = lambda v: json.dumps(v, separators=(',', ':'))
                row = (packet['reception_id'], packet['received_at'], now, packet['kind'], packet['route_type'],
                       int(packet['route_type'] in (0,3)), packet['transport_code'], packet['payload'], packet['raw'],
                       packet['digest'], packet['client_digest'], packet['metadata'], packet['rssi'], packet['snr'],
                       packet['count'], packet['size'], packet['path_raw'], j(attribution['route']),
                       j(attribution['positions']), attribution['first_hop'], attribution['middle_hop'], attribution['last_hop'],
                       j(attribution['previous']), j(attribution['following']), attribution['confidence'],
                       attribution['ambiguous'], attribution['evidence'], now)
                grouped.setdefault(key, []).append(row)
        for key, rows in grouped.items():
            try:
                # Check before making either directory or file. Never prune to make room.
                if shutil.disk_usage(Path(main_path).parent).free < MIN_FREE_BYTES:
                    raise OSError('Collection paused: less than 64 MiB free disk space; existing history is preserved.')
                _write(statistics_path(main_path, key), rows)
                results[key] = len(rows)
            except (OSError, sqlite3.Error) as exc:
                errors[key] = dict(error=str(exc), dropped=len(rows))
    return results, errors


def snapshot(main_path, selected=None):
    """Status reads never initialize a statistics file or modify recorded data."""
    with closing(open_database(Path(main_path).as_uri()+'?mode=ro', timeout=2)) as db:
        rows = [dict(r) for r in db.execute('''SELECT v.public_key,r.name FROM voltage_config v
            LEFT JOIN repeaters r ON r.public_key=v.public_key
            WHERE v.managed=1 AND v.public_key!='' ORDER BY r.name COLLATE NOCASE,v.public_key''')]
    if selected and selected not in {r['public_key'] for r in rows}:
        raise ValueError('Select a managed repeater.')
    selected = selected or (rows[0]['public_key'] if rows else '')
    status = dict(observation_count=0, last_recorded_at=None, last_received_at=None, error='')
    if selected:
        path = statistics_path(main_path, selected)
        if path.exists():
            try:
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=0.25)) as db:
                    db.row_factory=sqlite3.Row
                    row=db.execute('SELECT * FROM collection_health WHERE id=1').fetchone()
                    if row: status.update(dict(row))
            except (OSError, sqlite3.Error) as exc:
                status['observation_count'] = None
                status['error'] = 'Saved statistics unavailable: '+str(exc)
    return dict(ok=True, repeaters=rows, selected=selected, **status)


COVERAGE_SCHEMA = """CREATE TABLE IF NOT EXISTS collection_windows(
 id INTEGER PRIMARY KEY, started_at REAL NOT NULL, ended_at REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS collection_windows_time ON collection_windows(ended_at,started_at);"""


def record_coverage(main_path, started_at, ended_at):
    """Local collector uptime only; never creates files or collects RF data.

    Called only after a connected, healthy, drained interval. Loss/connection
    changes reset the interval before this writer runs. Existing history remains.
    """
    if ended_at<=started_at:return
    with MEMBERSHIP_LOCK, closing(open_database(Path(main_path).as_uri()+'?mode=ro',timeout=.25)) as main:
        for cfg in main.execute("SELECT public_key,statistics_since_ns FROM voltage_config WHERE managed=1 AND public_key!=''"):
            path=statistics_path(main_path,cfg['public_key'])
            if not path.exists():continue
            lo=max(started_at,cfg['statistics_since_ns']/1e9)
            if lo>=ended_at:continue
            if shutil.disk_usage(path.parent).free<MIN_FREE_BYTES:raise OSError('Coverage recording paused: low disk space.')
            with closing(sqlite3.connect(path,timeout=.25)) as db:
                db.executescript(COVERAGE_SCHEMA)
                with db:
                    last=db.execute('SELECT id,started_at,ended_at FROM collection_windows ORDER BY ended_at DESC LIMIT 1').fetchone()
                    if last and lo<=last[2]+.001 and lo>=last[1]:
                        db.execute('UPDATE collection_windows SET ended_at=MAX(ended_at,?) WHERE id=?',(ended_at,last[0]))
                    else:db.execute('INSERT INTO collection_windows(started_at,ended_at) VALUES(?,?)',(lo,ended_at))



def active_keys(main_path):
    with closing(open_database(Path(main_path).as_uri()+'?mode=ro',timeout=.25)) as db:
        return {r[0] for r in db.execute("SELECT public_key FROM voltage_config WHERE managed=1 AND public_key!=''")}
