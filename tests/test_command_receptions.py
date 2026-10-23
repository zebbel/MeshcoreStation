"""Reception evidence must never become a second command execution."""
import asyncio
import hashlib
import hmac
import sqlite3
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from Crypto.Cipher import AES
from meshcorestation.radio.companion import Companion
from meshcorestation.storage import database, reception_store as store
from meshcorestation.web import maps

KEY = b'1234567890123456'


def packet(path='aa', text='Alice: ping', stamp=123, key=KEY, scope=None):
    clear = stamp.to_bytes(4, 'little') + b'\0' + text.encode()
    clear += bytes(-len(clear) % 16)
    cipher = AES.new(key, AES.MODE_ECB).encrypt(clear)
    payload = hashlib.sha256(key).digest()[:1] + hmac.new(key, cipher, hashlib.sha256).digest()[:2] + cipher
    rx = dict(payload_type=5, route_type=0 if scope else 1, pkt_payload=payload,
              path=path, path_len=len(path)//2, path_hash_size=1, rssi=-100, snr=3,
              chan_name='Public', sender_timestamp=stamp, message=text)
    if scope:
        code = int.from_bytes(hmac.new(scope, b'\x05'+payload, hashlib.sha256).digest()[:2], 'little')
        code = 1 if code == 0 else 65534 if code == 65535 else code
        rx['transport_code'] = (code.to_bytes(2, 'little')*2).hex()
    return rx


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_FILE', tmp_path/'station.db')
    instance = database.Database(Mock())
    yield instance
    instance.close()


def test_authenticated_duplicates_before_during_after_command_execute_once(db):
    async def scenario():
        c = Companion(Mock(), db)
        c.tracking_key = KEY
        c.channel_idx, c.channel_name, c.channel_hash = 0, 'Public', hashlib.sha256(KEY).hexdigest()[:2]
        executions, replies = [], []
        async def handle(*args):
            executions.append(args)
            c._handle_rx_log(NS(payload=packet('aabb')))
            return 'pong'
        async def send(*args):
            replies.append(args)
            return 'unscoped'
        c.bot = NS(match_command=lambda text: {'trigger':'ping'} if text == 'ping' else None, handle_message=handle)
        c.send_channel_message = send
        first = packet('aa')
        c._handle_rx_log(NS(payload=first))
        c._handle_rx_log(NS(payload=dict(first, rssi=-90)))
        event = NS(payload=dict(channel_idx=0, text='Alice: ping', sender_timestamp=123, path_len=1, path_hash_mode=0))
        await c._handle_channel_message(event)
        c._handle_rx_log(NS(payload=packet('bb')))
        await c._handle_channel_message(event)
        assert len(executions) == len(replies) == 1
        rows = db.db.execute('SELECT * FROM logger').fetchall()
        assert len(rows) == 1 and rows[0]['reply'] == 'pong' and rows[0]['command_status'] == 'completed'
        paths = store.paths(db.db, rows[0]['id'])
        assert [p['rx_path'] for p in paths] == ['aa', 'aabb', 'bb']
        assert [o['rssi'] for o in paths[0]['observations']] == [-100, -90]
        assert all(o['recv_time'] > 0 for p in paths for o in p['observations'])
        # Recording new routes does not change the first path used for replies.
        assert replies[0][2]['path'] == 'aa'
        assert c.active_command_id is None
    asyncio.run(scenario())


def test_ambiguous_delivery_route_records_all_without_guessing_reply_scope(db):
    c = Companion(Mock(), db)
    c.tracking_key = KEY
    c.channel_idx, c.channel_name, c.channel_hash = 0, 'Public', hashlib.sha256(KEY).hexdigest()[:2]
    c.bot = NS(match_command=lambda text: {'trigger':'ping'})
    for path in ('aa', 'bb'):
        c._handle_rx_log(NS(payload=packet(path)))
    assert c._find_matching_rx(dict(raw_text='Alice: ping', sender_timestamp=123, path_len=1, path_hash_mode=0)) is None
    identity = store.channel_identity(KEY, 123, 'Alice: ping')
    command = db.add_logger(dict(name='Alice', message='ping'), None, 'unknown', '')
    store.bind(db.db, identity, command)
    assert [p['rx_path'] for p in store.paths(db.db, command)] == ['aa', 'bb']


def test_authentication_and_identity_do_not_cross_channels_timestamps_or_scopes(db):
    rx = packet()
    assert store.authenticate(rx, b'abcdefghijklmnop') is None
    assert store.authenticate(dict(rx, pkt_payload=rx['pkt_payload'][:-1]+b'x'), KEY) is None
    original = store.authenticate(rx, KEY)
    assert store.authenticate(packet(stamp=124), KEY)[0] != original[0]
    assert store.authenticate(packet(text='Other: ping'), KEY)[0] != original[0]
    secret = b'abcdefghijklmnop'
    scoped = packet(scope=secret)
    assert store.authenticate(scoped, KEY, []) is None
    authenticated = store.authenticate(scoped, KEY, [{'scope_key':secret.hex()}])
    assert authenticated[1] != original[1]
    identity = original[0]
    command = db.add_logger(dict(name='Alice', message='ping'), rx, 'unscoped', '')
    store.record(db.db, identity, rx, original[1])
    store.bind(db.db, identity, command, original[1])
    store.record(db.db, identity, packet('bb', scope=secret), authenticated[1])
    assert [p['rx_path'] for p in store.paths(db.db, command)] == ['aa']
    assert KEY.hex() not in str(store.paths(db.db, command))


def test_unidentifiable_scope_association_is_not_guessed(db):
    identity = store.channel_identity(KEY,123,'Alice: ping')
    command = db.add_logger(dict(name='Alice', message='ping'), None, 'unknown', '')
    store.record(db.db, identity, packet(), 'scope-one')
    store.record(db.db, identity, packet('bb'), 'scope-two')
    store.bind(db.db, identity, command)
    assert store.paths(db.db,command) == []


def test_migration_is_additive_idempotent_and_retains_legacy_route(tmp_path, monkeypatch):
    file = tmp_path/'legacy.db'
    conn = sqlite3.connect(file)
    conn.executescript('CREATE TABLE logger(id INTEGER PRIMARY KEY, recv_time INTEGER, rx_path TEXT); INSERT INTO logger VALUES(1,123,"aabb");')
    conn.close()
    monkeypatch.setattr(database, 'DB_FILE', file)
    instance = database.Database(Mock())
    instance.create_database()
    assert tuple(instance.db.execute('SELECT id,recv_time,rx_path FROM logger').fetchone()) == (1,123,'aabb')
    assert store.paths(instance.db,1) == []
    instance.close()


def test_map_variants_share_endpoints_and_calculate_each_route(db, monkeypatch):
    db.save_companion_position('11'*32, 'Alice', 50, 8, 0)
    db.save_companion_position('22'*32, 'Bot', 50, 9, 0, is_bot=True)
    for key, name, lat, lon in [('aa'+'11'*31,'Hill',50.1,8.5),('bb'+'22'*31,'Valley',51,8.5)]:
        db.db.execute('INSERT INTO repeaters(public_key,name,latitude,longitude,first_seen,last_seen) VALUES(?,?,?,?,1,1)', (key,name,lat,lon))
    db.db.commit()
    command = db.add_logger(dict(name='Alice', message='ping', path_len=1), packet(), 'unscoped', '')
    identity = store.channel_identity(KEY,123,'Alice: ping')
    store.bind(db.db,identity,command,'unscoped')
    for path in ('aa','bb','ff','aabb'):
        store.record(db.db,identity,packet(path))
    monkeypatch.setattr(maps.data,'DB_PATH',database.DB_FILE)
    result = maps.route_map(command)
    routes = result['reception_paths']
    assert len(routes) == 4 and result['hops'] == routes[0]['hops']
    assert routes[0]['route_distance_km'] < routes[1]['route_distance_km']
    assert routes[2]['route_distance_lower_bound']
    assert routes[3]['route_distance_km'] > routes[0]['route_distance_km']
    assert all(r['nodes'][0] == routes[0]['nodes'][0] and r['nodes'][-1] == routes[0]['nodes'][-1] for r in routes)
    assert routes[2]['hops'][0]['status'] == 'Unknown repeater'
    # Invalid path lengths remain explicit, rather than drawing invented hops.
    store.record(db.db,identity,dict(packet('aa'),path_len=2))
    assert not maps.route_map(command)['reception_paths'][-1]['path_valid']


def test_late_receptions_and_clock_changes_keep_first_recorded_path(db):
    identity = store.channel_identity(KEY,123,'Alice: ping')
    command = db.add_logger(dict(name='Alice',message='ping'),None,'unknown','')
    store.bind(db.db,identity,command)
    assert store.paths(db.db,command) == []
    store.record(db.db,identity,packet('aa'),now=2000)
    store.record(db.db,identity,packet('bb'),now=1000)
    assert [p['rx_path'] for p in store.paths(db.db,command)] == ['aa','bb']
    store.record(db.db,identity,dict(packet('aa'),snr=None,rssi=None),now=3000)
    assert len(store.paths(db.db,command)[0]['observations']) == 2
    # The persistent binding also prevents a second delivery after restart.
    assert store.existing(db.db,identity) == command
