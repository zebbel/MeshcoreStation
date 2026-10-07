import sqlite3
import pytest
from meshcorestation.web import maps


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path/'routes.db'
    db = sqlite3.connect(path)
    db.executescript('''
        CREATE TABLE logger (id INTEGER, message TEXT, sender TEXT, sender_latitude REAL, sender_longitude REAL, rx_path TEXT, path_len INTEGER, path_hash_size INTEGER);
        CREATE TABLE repeaters (public_key TEXT, name TEXT, latitude REAL, longitude REAL);
        CREATE TABLE companion_positions (public_key TEXT, name TEXT, latitude REAL, longitude REAL, is_bot INTEGER);
        INSERT INTO companion_positions VALUES ('bb', 'Base', 50, 9, 1);
        INSERT INTO repeaters VALUES ('aa11', 'Hill repeater', 50.1, 8.5);
    ''')
    monkeypatch.setattr(maps.data,'DB_PATH',path)
    yield db
    db.close()


def add(db, command, path='aa', count=1, lat=50):
    db.execute('INSERT INTO logger VALUES (1, ?, ?, ?, ?, ?, ?, 1)', (command,'Alice',lat,8,path,count))
    db.commit()


@pytest.mark.parametrize('command',['ping','status','?','position','scope add local','custom hello'])
def test_every_command_has_route_and_distances(database, command):
    add(database, command)
    result = maps.route_map(1)
    assert [node['label'] for node in result['nodes']]==['Alice','Hill repeater','Base']
    assert result['hops'][0]['name']=='Hill repeater'
    assert len(result['segments'])==2
    assert result['route_distance_km'] > result['direct_distance_km'] > 0
    assert not result['route_distance_lower_bound']


@pytest.mark.parametrize('ambiguous',[False,True])
def test_unknown_or_ambiguous_hop_is_not_guessed(database,ambiguous):
    if ambiguous:
        database.execute("INSERT INTO repeaters VALUES ('aa22','Other',51,8)")
    add(database,'status',path='aa' if ambiguous else 'ff')
    result=maps.route_map(1)
    assert not result['segments']
    assert result['route_distance_lower_bound']
    assert result['route_distance_km']==result['direct_distance_km']
    assert result['hops'][0]['name'] in ('aa','ff')


def test_missing_metadata_and_position(database):
    add(database,'?',path=None,count=None,lat=None)
    result=maps.route_map(1)
    assert not result['path_valid']
    assert result['direct_distance_km'] is None
    assert result['route_distance_km'] is None
    assert not result['segments']
    assert maps.route_map(99) is None


def test_direct_packet(database):
    add(database,'status',path='',count=0)
    result=maps.route_map(1)
    assert result['path_valid'] and not result['hops']
    assert result['direct_distance_km']==result['route_distance_km']
    assert len(result['segments'])==1


def test_named_repeater_without_coordinates(database):
    database.execute('UPDATE repeaters SET latitude=NULL')
    add(database,'status')
    result=maps.route_map(1)
    assert result['hops'][0]['name']=='Hill repeater'
    assert result['hops'][0]['status']=='Coordinates missing'
    assert result['route_distance_lower_bound']
