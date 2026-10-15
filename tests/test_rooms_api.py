from flask import Flask
import pytest
from meshcorestation.web import rooms_api
from meshcorestation.rooms.service import RoomService


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(rooms_api,'DATA_DIR',tmp_path)
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
    assert path.joinpath('rooms.db').stat().st_mode & 0o777 == 0o600
    assert http.post('/api/rooms',json={'action':'post','room':rid,'text':'disabled'},headers=headers).status_code==400
    assert http.post('/api/rooms',json={'action':'enabled','room':rid,'enabled':'true'},headers=headers).status_code==400
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
