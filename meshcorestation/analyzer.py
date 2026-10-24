"""On-demand read-only Analyzer integration. No worker, radio, cookies or browser identity.

Fixtures verify response formats only, not live access or provider permission.
Access restrictions are surfaced as errors without any attempt to bypass them.
"""
from contextlib import contextmanager
import json
import math
import re
import sqlite3
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from meshcorestation.config import DATA_DIR

HOST = 'https://analyzer.meshcorenetz.de'
TTL = 300
MAX_BODY = 2 * 1024 * 1024
ENDPOINTS = {
    'detail': '/api/nodes/{key}/detail?hours=24',
    'neighbors': '/api/nodes/{key}/neighbors',
    'reach': '/api/nodes/{key}/reach?days=1',
    'metrics': '/api/graph/metrics/{key}',
    'clock': '/api/nodes/{key}/clock-skew?hours=24',
    'direct': '/api/nodes/{key}/direct-packets?since=24',
    'beacons': '/api/channels/beacons?hours=720&node={key}',
    'sensors': '/api/channels/sensors?hours=720&node={key}',
}

class AnalyzerError(Exception):
    def __init__(self, state, message):
        self.state = state
        super().__init__(message)


def public_key(key):
    if not isinstance(key, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', key):
        raise ValueError('Select a valid 64-character repeater public key.')
    return key.lower()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def transport(url, headers, timeout):
    """Fixed-host caller; reject redirects, limit body and socket wait."""
    req = Request(url, headers={'Accept': 'application/json',
                               'User-Agent': 'MeshcoreStation/4.0.4 (on-demand analyzer client)', **headers})
    try:
        with build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            deadline = time.monotonic() + timeout
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline:
                    raise AnalyzerError('unavailable', 'External monitoring request timed out.')
                chunk = response.read1(min(65536, MAX_BODY+1-size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                if size > MAX_BODY:
                    raise AnalyzerError('invalid', 'Analyzer response exceeds the size limit.')
            body = b''.join(chunks)
            return response.status, dict(response.headers), body
    except HTTPError as exc:
        # Never read error pages, follow redirects or reuse browser headers.
        return exc.code, {}, b''
    except (TimeoutError, URLError, OSError) as exc:
        raise AnalyzerError('unavailable', 'External monitoring unavailable: request timed out or connection failed.') from exc


def validate(name, body, key):
    """Validate captured envelopes and nested rows; retain unknown optional fields."""
    try:
        value = json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise AnalyzerError('invalid', 'Analyzer returned malformed JSON.') from exc
    def fail():
        raise AnalyzerError('invalid', 'Analyzer response format is invalid (' + name + ').')
    def obj(v):
        if not isinstance(v, dict): fail()
    def rows(v):
        if not isinstance(v, list) or len(v) > 20000 or any(not isinstance(r, dict) for r in v): fail()
    if name == 'neighbors': rows(value)
    else:
        obj(value)
        required = {'detail': ('node', 'stat'), 'reach': ('neighbourList',),
                    'metrics': ('degree',), 'clock': ('samples', 'recentHashEvidence'),
                    'direct': ('rows',), 'beacons': ('beacons',), 'sensors': ('readings',)}[name]
        if any(k not in value for k in required): fail()
        if name == 'detail':
            obj(value['node']); obj(value['stat'])
            if value['node'].get('id') != key: fail()
            for field in ('heardBy','timeline','packetTypes','hopDist','carriedTypes','hopTrend',
                          'recentPackets','pathsThroughNode','snrTrend','relayTimeline','relayNeighbours','relayRegions'):
                if field not in value: fail()
                rows(value[field])
            for row in value['pathsThroughNode']:
                if not isinstance(row.get('path'), list) or any(not isinstance(p,str) or not re.fullmatch('[0-9a-fA-F]{1,64}',p) for p in row['path']): fail()
        elif name == 'reach': rows(value['neighbourList'])
        elif name == 'metrics':
            if value.get('id') != key: fail()
        elif name == 'clock':
            rows(value['samples']); rows(value['recentHashEvidence'])
        else: rows(value[required[0]])
    # Reject unexpected nested values in fields consumed as numbers or labels.
    numeric = {'degree','betweenness','rank','receptions','observers','relayCount24h','relayCount1h',
               'pairsServed','count','Count','total','toCount','fromCount','weHear','theyHear','twoWayCount',
               'directObservers','distanceKm','DistanceKm','lat','lon','SNR','RSSI','sampleCount'}
    strings = {'name','Name','pubkey','ID','id','Conf','confidence','Provenance','bucket','lastSeen','firstSeen','packetType','hash'}
    def check(v, depth=0):
        if depth > 20: fail()
        if isinstance(v, dict):
            for k, item in v.items():
                if k in numeric and item is not None and (type(item) not in (int,float) or not math.isfinite(item)): fail()
                if k in strings and item is not None and not isinstance(item,str): fail()
                check(item, depth+1)
        elif isinstance(v,list):
            for item in v: check(item, depth+1)
    check(value)
    return value


class AnalyzerService:
    def __init__(self, path=None, fetch=transport, clock=time.time):
        self.path = path or DATA_DIR / 'analyzer-cache.db'
        self.fetch, self.clock = fetch, clock
        self.lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.revisions = {}
        self.blocked_until = 0
        self.blocked_error = None

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=3)
        db.execute('CREATE TABLE IF NOT EXISTS analyzer_cache (public_key TEXT PRIMARY KEY, fetched_at REAL NOT NULL, payload TEXT NOT NULL, validators TEXT NOT NULL)')
        try:
            with db: yield db
        finally:
            db.close()

    def cached(self, key):
        with self.connection() as db:
            row = db.execute('SELECT fetched_at,payload,validators FROM analyzer_cache WHERE public_key=?', (key,)).fetchone()
        if not row: return None
        try: return row[0], json.loads(row[1]), json.loads(row[2])
        except (ValueError,TypeError): return None

    def remove(self, key):
        key = public_key(key)
        with self.cache_lock:
            self.revisions[key] = self.revisions.get(key, 0)+1
            if self.path.exists():
                with self.connection() as db:
                    db.execute('DELETE FROM analyzer_cache WHERE public_key=?', (key,))

    def snapshot(self, key, force=False, cache_only=False):
        key = public_key(key)
        with self.cache_lock:
            revision = self.revisions.get(key, 0)
            previous = self.cached(key)
        now = self.clock()
        stale = previous is None or not 0 <= now-previous[0] < TTL
        result = {'ok': True, 'public_key': key, 'experimental': True, 'live_verified': False,
                  'data': previous[1] if previous else None,
                  'fetched_at': previous[0] if previous else None, 'stale': stale,
                  'state': 'cached' if previous else 'empty', 'error': None}
        if now < self.blocked_until:
            return {**result, 'state': self.blocked_error.state, 'error': str(self.blocked_error)}
        if cache_only: return result
        if previous and not stale and not force: return result
        if not self.lock.acquire(blocking=False):
            return {**result, 'state': 'busy', 'error': 'An external monitoring request is already running. Reopen to read its result.'}
        try:
            data, validators = {}, {}
            deadline = time.monotonic() + 25
            for name, template in ENDPOINTS.items():
                old_headers = previous[2].get(name, {}) if previous else {}
                for attempt in range(2):
                    remaining = deadline-time.monotonic()
                    if remaining <= 0: raise AnalyzerError('unavailable', 'External monitoring request timed out.')
                    status, headers, body = self.fetch(HOST+template.format(key=key), old_headers, min(3,remaining))
                    if status not in (502,503,504) or attempt: break
                    time.sleep(.1)  # one bounded retry, transient gateway failures only
                if status == 403:
                    self.blocked_until = self.clock()+TTL
                    self.blocked_error = AnalyzerError('blocked', 'External monitoring unavailable: Analyzer denied access (HTTP 403 / possible Cloudflare 1010). No bypass or automatic retry will be attempted during the five-minute cooldown.')
                    raise self.blocked_error
                if status == 429:
                    self.blocked_until = self.clock()+TTL
                    self.blocked_error = AnalyzerError('rate_limited', 'External monitoring unavailable: Analyzer rate limit (HTTP 429). Wait five minutes before retrying.')
                    raise self.blocked_error
                if status == 304 and previous:
                    data[name], validators[name] = previous[1][name], old_headers
                    continue
                if status != 200: raise AnalyzerError('unavailable', f'External monitoring unavailable: Analyzer HTTP {status}.')
                if len(body) > MAX_BODY: raise AnalyzerError('invalid', 'Analyzer response exceeds the size limit.')
                data[name] = validate(name, body, key)
                headers = {k.lower():v for k,v in headers.items()}
                validators[name] = {out:headers[src] for src,out in [('etag','If-None-Match'),('last-modified','If-Modified-Since')] if src in headers}
            at = self.clock()
            with self.cache_lock:
                if self.revisions.get(key, 0) != revision:
                    return {**result, 'data': None, 'fetched_at': None, 'stale': True,
                            'state': 'removed', 'error': 'Repeater removed during refresh; snapshot discarded.'}
                with self.connection() as db:
                    db.execute('INSERT OR REPLACE INTO analyzer_cache VALUES (?,?,?,?)',
                               (key, at, json.dumps(data, allow_nan=False), json.dumps(validators)))
            return {**result, 'data': data, 'fetched_at': at, 'stale': False, 'state': 'available'}
        except AnalyzerError as exc:
            return {**result, 'state': exc.state, 'error': str(exc)}
        except (TimeoutError, URLError, OSError):
            return {**result, 'state': 'unavailable', 'error': 'External monitoring unavailable: request timed out or connection failed.'}
        finally:
            self.lock.release()

service = AnalyzerService()
