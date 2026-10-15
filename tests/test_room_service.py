import pytest
from meshcorestation.rooms.service import RoomService
A='ab'*32
B='cd'*32

@pytest.fixture
def room(tmp_path):
    service=RoomService(tmp_path/'rooms.db',clock=lambda:1000)
    rid=service.create('Discussion')
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
    other=service.create('Other');service.set_enabled(other,True)
    service.grant(other,B,'writer')
    post=service.post(rid,A,1,'private')
    assert service.synchronize(other,B,0)==[]
    service.acknowledge(rid,B,post['timestamp'])
    with pytest.raises(ValueError):service.acknowledge(rid,B,999)
    with service.connect() as db:
        assert db.execute('SELECT timestamp FROM cursors').fetchone()[0]==post['timestamp']
    with pytest.raises(ValueError):service.post(rid,A,2,'x'*152)
