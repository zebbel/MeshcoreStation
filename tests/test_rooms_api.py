import os
import sqlite3
from flask import Flask
import pytest
from meshcorestation.web import rooms_api
from meshcorestation.rooms.service import RoomService


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(rooms_api,'DATA_DIR',tmp_path)
    monkeypatch.setattr(rooms_api,'DB_PATH',tmp_path / 'station.db')
    app=Flask(__name__);rooms_api.register_room_routes(app)
    return app.test_client(),tmp_path


def test_local_api_controls_secrets_and_persistence(client):
    http,path=client
    headers={'X-Meshcore-Control':'1'}
    assert http.get('/api/rooms').status_code==403
    assert http.post('/api/rooms',json={'action':'create','name':'Board'},headers={**headers,'Origin':'https://evil.example'}).status_code==403
    response=http.post('/api/rooms',json={'action':'create','name':'Board'},headers=headers)
    data=response.get_json();assert response.status_code==200
    room=data['rooms'][0];rid=room['id'];public=room['public_key']
    assert not room['enabled'] and room['contact_uri'].endswith('type=3')
    assert 'seed' not in response.text
    if os.name != 'nt':  # Windows ACLs do not map to POSIX mode bits.
        assert path.joinpath('rooms.db').stat().st_mode & 0o777 == 0o600
    assert http.post('/api/rooms',json={'action':'post','room':rid,'text':'disabled'},headers=headers).status_code==400
    assert http.post('/api/rooms',json={'action':'enabled','room':rid,'enabled':'true'},headers=headers).status_code==400
    assert http.post('/api/rooms',json={'action':'password','room':rid,'password':'room-test'},headers=headers).status_code==200
    assert http.post('/api/rooms',json={'action':'enabled','room':rid,'enabled':True},headers=headers).status_code==200
    assert http.post('/api/rooms',json={'action':'grant','room':rid,'key':'aa'*32,'role':'writer'},headers=headers).status_code==200
    assert http.post('/api/rooms',json={'action':'scope','room':rid,'scope_key':'bad'},headers=headers).status_code==400
    assert http.post('/api/rooms',json={'action':'post','room':rid,'text':'Hello from dashboard'},headers=headers).status_code==200
    saved=RoomService(path/'rooms.db').details(rid)
    assert saved['public_key']==public and len(saved['posts'])==1
    assert http.get('/rooms').status_code==200


def test_bounds_and_type_errors(client):
    http,path=client;headers={'X-Meshcore-Control':'1'}
    for _ in range(4):
        assert http.post('/api/rooms',json={'action':'create','name':'Room'},headers=headers).status_code==200
    assert http.post('/api/rooms',json={'action':'create','name':'Fifth'},headers=headers).status_code==400
    assert http.post('/api/rooms',json=[],headers=headers).status_code==400
    assert http.post('/api/rooms',json={'action':'post','room':1,'text':'x'*9000},headers=headers).status_code==400
    assert http.post('/api/rooms',json={'action':'enabled','room':True,'enabled':True},headers=headers).status_code==400


def test_room_qr_uses_room_identity_and_type(client,monkeypatch):
    import base64
    import qrcode
    from urllib.parse import urlsplit,parse_qs
    http,path=client;headers={'X-Meshcore-Control':'1'}
    room=http.post('/api/rooms',json={'action':'create','name':'My room'},headers=headers).json['rooms'][0]
    encoded=[];make=qrcode.make
    def capture(data,**kwargs):
        encoded.append(data);return make(data,**kwargs)
    monkeypatch.setattr(qrcode,'make',capture)
    response=http.post('/api/rooms',json={'action':'qr','room':room['id']},headers=headers)
    assert response.status_code==200
    card=response.json
    assert encoded==[card['uri']]==[room['contact_uri']]
    query=parse_qs(urlsplit(card['uri']).query)
    assert query['type']==['3'] and query['public_key']==[room['public_key']]
    assert query['name']==['My room']
    assert b'<svg' in base64.b64decode(card['image'].split(',',1)[1])
    assert 'seed' not in card and 'scope_key' not in card
    assert http.post('/api/rooms',json={'action':'qr','room':room['id']}).status_code==403


def test_password_never_returned_and_scope_removed(client):
    http,path=client;headers={'X-Meshcore-Control':'1'}
    room=http.post('/api/rooms',json={'action':'create','name':'Private'},headers=headers).json['rooms'][0]
    rid=room['id']
    assert 'scope_key' not in room and not room['auth_revision']
    assert http.post('/api/rooms',json={'action':'enabled','room':rid,'enabled':True},headers=headers).status_code==400
    secret='my-room-pass'
    response=http.post('/api/rooms',json={'action':'password','room':rid,'password':secret},headers=headers)
    assert response.status_code==200 and response.json['rooms'][0]['auth_revision']==1
    assert secret not in response.text and 'password_hash' not in response.text
    assert http.post('/api/rooms',json={'action':'scope','room':rid,'scope_key':''},headers=headers).status_code==400
    qr=http.post('/api/rooms',json={'action':'qr','room':rid},headers=headers)
    assert secret not in qr.text and 'password=' not in qr.json['uri']


def test_delete_room_requires_disabled_confirmation_and_removes_only_its_data(client):
    http, path = client
    headers = {'X-Meshcore-Control': '1'}
    def post(**body):
        return http.post('/api/rooms', json=body, headers=headers)
    first = post(action='create', name='To delete').json['rooms'][0]
    second = post(action='create', name='Keep me').json['rooms'][1]
    rid = first['id']
    service = RoomService(path / 'rooms.db')
    assert post(action='password', room=rid, password='secret').status_code == 200
    assert post(action='enabled', room=rid, enabled=True).status_code == 200
    assert post(action='grant', room=rid, key='aa'*32, role='writer').status_code == 200
    assert post(action='post', room=rid, text='Delete this message').status_code == 200
    expected = {'name': first['name'], 'public_key': first['public_key']}
    assert post(action='delete', room=rid, confirm_delete=True, expected=expected).status_code == 400
    assert post(action='enabled', room=rid, enabled=False).status_code == 200
    assert post(action='delete', room=rid, expected=expected).status_code == 400
    assert post(action='delete', room=rid, confirm_delete=True, expected={**expected,'name':'Wrong'}).status_code == 400
    assert post(action='delete', room=rid, confirm_delete=True, expected={**expected,'public_key':'bb'*32}).status_code == 400
    assert post(action='delete', room=True, confirm_delete=True, expected=expected).status_code == 400
    service.set_bot(rid)
    assert post(action='delete', room=rid, confirm_delete=True, expected=expected).status_code == 400
    service.clear_bot()
    with service.connect() as db:
        db.execute('INSERT INTO sessions_replay VALUES (?,?,?)', (rid, 'aa'*32, 1))
        db.execute('INSERT INTO replay VALUES (?,?,?)', (rid, 'aa'*32, 1))
        db.execute('INSERT INTO cursors VALUES (?,?,?)', (rid, 'aa'*32, 1))
    deleted = post(action='delete', room=rid, confirm_delete=True, expected=expected)
    assert deleted.status_code == 200, deleted.json
    assert [r['id'] for r in deleted.json['rooms']] == [second['id']]
    with service.connect() as db:
        for table in ('room_auth','identities','sessions_replay','members','posts','replay','cursors'):
            assert db.execute(f'SELECT COUNT(*) FROM {table} WHERE room_id=?', (rid,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM rooms WHERE id=?',(rid,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM identities WHERE room_id=?',(second['id'],)).fetchone()[0] == 1
    assert post(action='delete', room=rid, confirm_delete=True, expected=expected).status_code == 400
    assert post(action='create', name='Replacement').status_code == 200



def test_room_deletion_blocks_managed_battery_report_destinations(client):
    http, path = client
    headers = {'X-Meshcore-Control': '1'}
    def post(**body):
        return http.post('/api/rooms', json=body, headers=headers)
    room = post(action='create', name='Battery destination').json['rooms'][0]
    rid = room['id']
    expected = {'name': room['name'], 'public_key': room['public_key']}
    with sqlite3.connect(path / 'station.db') as station:
        station.execute('CREATE TABLE voltage_config ('
                        'id INTEGER PRIMARY KEY, public_key TEXT, '
                        'managed INTEGER NOT NULL, report_target TEXT)')
        station.execute('INSERT INTO voltage_config VALUES (1, ?, 1, ?)',
                        ('ab'*32, f'room:{rid}'))
    denied = post(action='delete', room=rid, confirm_delete=True, expected=expected)
    assert denied.status_code == 400
    assert 'battery report destination' in denied.json['error']
    assert RoomService(path / 'rooms.db').config(rid)['public_key'] == room['public_key']
    with sqlite3.connect(path / 'station.db') as station:
        station.execute("UPDATE voltage_config SET report_target='bot' WHERE id=1")
    assert post(action='delete', room=rid, confirm_delete=True, expected=expected).status_code == 200


def test_room_deletion_blocks_legacy_battery_destination_before_schema_upgrade(client):
    http, path = client
    headers = {'X-Meshcore-Control': '1'}
    room = http.post('/api/rooms', json={'action': 'create', 'name': 'Legacy'}, headers=headers).json['rooms'][0]
    with sqlite3.connect(path / 'station.db') as station:
        station.execute('CREATE TABLE voltage_config (id INTEGER PRIMARY KEY, report_target TEXT)')
        station.execute('INSERT INTO voltage_config VALUES (?, ?)', (1, f"room:{room['id']}"))
    attempt = http.post('/api/rooms', json={'action': 'delete', 'room': room['id'],
        'confirm_delete': True, 'expected': {'name': room['name'], 'public_key': room['public_key']}}, headers=headers)
    assert attempt.status_code == 400
    assert RoomService(path / 'rooms.db').config(room['id'])['name'] == 'Legacy'
