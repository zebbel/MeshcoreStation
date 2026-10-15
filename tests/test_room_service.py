import pytest
from meshcorestation.rooms.service import RoomService
A='ab'*32
B='cd'*32

@pytest.fixture
def room(tmp_path):
    service=RoomService(tmp_path/'rooms.db',clock=lambda:1000)
    rid=service.create('Discussion');service.set_password(rid,'room-test')
    service.grant(rid,A,'writer');service.grant(rid,B,'reader')
    return service,rid


def test_default_disabled_and_permissions(room):
    service,rid=room
    with pytest.raises(PermissionError):service.post(rid,A,1,'hello')
    service.set_enabled(rid,True)
    with pytest.raises(PermissionError):service.post(rid,B,1,'hello')
    with pytest.raises(PermissionError):service.synchronize(rid,'ef'*32,0)
    post=service.post(rid,A,1,'hello')
    assert service.synchronize(rid,B,0)==[post]
    assert service.synchronize(rid,A,0)==[]
    service.revoke(rid,B)
    with pytest.raises(PermissionError):service.synchronize(rid,B,0)


def test_idempotency_order_restart_and_disable(room):
    service,rid=room;service.set_enabled(rid,True)
    first=service.post(rid,A,10,'one')
    assert service.post(rid,A,10,'one')==first
    with pytest.raises(ValueError):service.post(rid,A,10,'changed')
    second=service.post(rid,A,11,'two')
    assert second['timestamp']==first['timestamp']+1
    restored=RoomService(service.path,clock=lambda:900)
    third=restored.post(rid,A,12,'three')
    assert third['timestamp']==second['timestamp']+1
    assert restored.synchronize(rid,B,first['timestamp'])==[second,third]
    with pytest.raises(ValueError):restored.post(rid,A,9,'old')
    service.set_enabled(rid,False)
    with pytest.raises(PermissionError):service.synchronize(rid,B,0)
    service.set_enabled(rid,True)
    assert len(service.synchronize(rid,B,0))==3


def test_room_isolation_and_ack(room):
    service,rid=room;service.set_enabled(rid,True)
    other=service.create('Other');service.set_password(other,'room-test');service.set_enabled(other,True)
    service.grant(other,B,'writer')
    post=service.post(rid,A,1,'private')
    assert service.synchronize(other,B,0)==[]
    service.acknowledge(rid,B,post['timestamp'])
    with pytest.raises(ValueError):service.acknowledge(rid,B,999)
    with service.connect() as db:
        assert db.execute('SELECT timestamp FROM cursors').fetchone()[0]==post['timestamp']
    with pytest.raises(ValueError):service.post(rid,A,2,'x'*152)


def test_password_validation_and_legacy_room_migration(tmp_path):
    service=RoomService(tmp_path/'rooms.db')
    rid=service.create('Legacy')
    with pytest.raises(ValueError,match='password'):
        service.set_enabled(rid,True)
    for password in ('', 'a'*16, '\0hidden', 'é'*8):
        with pytest.raises(ValueError):service.set_password(rid,password)
    service.set_password(rid,'a'*15);service.set_enabled(rid,True)
    public=service.identity(rid).public
    service.grant(rid,A,'writer');service.post(rid,A,1,'Preserved history')
    with service.connect() as db:
        assert db.execute('SELECT password_hash FROM room_auth').fetchone()[0]!=b'a'*15
        db.execute('DROP TABLE room_auth')  # old ACL-only release has no auth table
    upgraded=RoomService(service.path)
    assert not upgraded.config(rid)['enabled']
    assert upgraded.config(rid)['auth_revision']==0
    assert upgraded.identity(rid).public==public
    assert len(upgraded.details(rid)['posts'])==1
    upgraded.set_password(rid,'new');upgraded.set_enabled(rid,True)
    assert upgraded.login(rid,B,1,b'new')[0]=='writer'
