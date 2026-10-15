"""Room bot commands share the channel bot's SQLite command history."""
import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from meshcorestation.runtime import Runtime
from meshcorestation.storage.database import Database
from meshcorestation.web import data as web_data


SENDER = 'ab' * 32
SAME_NAME_OTHER_KEY = 'cd' * 32
ROOM = 3


def database(path):
    # Use the real schema and data access without opening a serial radio.
    db = Database.__new__(Database)
    db.logger = SimpleNamespace(info=lambda *a: None, warning=lambda *a: None)
    db.db = sqlite3.connect(path)
    db.db.row_factory = sqlite3.Row
    db.create_database()
    return db


class Bot:
    def __init__(self, reply='pong', error=None):
        self.reply, self.error = reply, error

    def match_command(self, text):
        return {'trigger': 'ping'} if text == 'ping' else None

    async def handle_message(self, message, rx, command):
        assert message['sender_public_key'] == SENDER
        assert message['room_name'] == 'Test room'
        assert rx['snr'] == 4.25
        if self.error:
            raise self.error
        return self.reply


class Service:
    def __init__(self, fail_after=None):
        self.posts = []
        self.fail_after = fail_after

    def local_post(self, room, part):
        assert room == ROOM
        if self.fail_after is not None and len(self.posts) >= self.fail_after:
            raise RuntimeError('Room post failed')
        self.posts.append(part)


def runtime(db, bot=None, service=None):
    bot, service = bot or Bot(), service or Service()

    async def sender_name(key):
        assert key == SENDER
        return 'Alice'

    companion = SimpleNamespace(bot=bot, room_bot_id=ROOM,
                                room_bot_name='Test room',
                                room_sender_name=sender_name)
    instance = SimpleNamespace(
        companion=companion, database=db, rooms=SimpleNamespace(service=service),
        logger=SimpleNamespace(info=lambda *a: None))
    return instance, service


def post():
    return dict(text='ping', author=SENDER, sender_timestamp=900, timestamp=1000)


def rx(route=0):
    return dict(route_type=route, payload_type=2, path_len=2 if route == 0 else None,
                path_hash_size=1 if route == 0 else None,
                path='aabb' if route == 0 else '', rssi=-97, snr=4.25,
                room_scope_name='Europe' if route == 0 else 'direct')


def entries(db):
    return [dict(row) for row in db.db.execute('SELECT * FROM logger ORDER BY id')]


def test_room_command_appears_in_shared_dashboard_history(tmp_path, monkeypatch):
    path = tmp_path / 'station.db'
    db = database(path)
    try:
        db.save_companion_position(SENDER, 'Old nickname', 49.1, 8.2, 120)
        # The display name may match a different radio contact: room key wins.
        db.save_companion_position(SAME_NAME_OTHER_KEY, 'Alice', 51.1, 10.2, 200)
        instance, service = runtime(db)
        asyncio.run(Runtime.handle_room_post(instance, ROOM, post(), rx()))
        assert service.posts == ['pong']
        row, = entries(db)
        assert row['type'] == 'room' and row['room_id'] == ROOM
        assert row['channel_name'] == 'Test room'
        assert row['message'] == 'ping' and row['sender'] == 'Alice'
        assert row['sender_timestamp'] == 900
        assert row['recv_time'] is not None
        assert row['sender_public_key'] == SENDER
        assert (row['sender_latitude'], row['sender_longitude'], row['sender_altitude']) == (49.1, 8.2, 120)
        assert row['scope_name'] == 'Europe'
        assert row['path_len'] == 2 and row['rx_path'] == 'aabb'
        assert row['rssi'] == -97 and row['snr'] == 4.25
        assert row['reply'] == 'pong' and row['command_status'] == 'completed'

        monkeypatch.setattr(web_data, 'DB_PATH', path)
        dashboard = web_data.snapshot()
        assert dashboard['total'] == 1
        assert dashboard['latest']['id'] == row['id']
        assert dashboard['rows'][0]['room_id'] == ROOM
        assert dashboard['commands'] == ['ping']
    finally:
        db.close()


def test_direct_room_command_is_logged_and_unrecognized_text_is_not(tmp_path):
    db = database(tmp_path / 'station.db')
    try:
        instance, service = runtime(db)
        asyncio.run(Runtime.handle_room_post(instance, ROOM, post(), rx(2)))
        row, = entries(db)
        assert row['scope_name'] == 'direct'
        assert row['path'] == 'direct' and row['path_len'] is None
        assert row['room_id'] == ROOM and row['reply'] == 'pong'
        unknown = dict(post(), text='random text')
        asyncio.run(Runtime.handle_room_post(instance, ROOM, unknown, rx(2)))
        assert len(entries(db)) == 1 and service.posts == ['pong']
    finally:
        db.close()


@pytest.mark.parametrize('answer,error,status', [
    (None, None, 'no reply'),
    (None, RuntimeError('Command processing failed'), 'failed'),
])
def test_room_history_finalized_without_reply(tmp_path, answer, error, status):
    db = database(tmp_path / 'station.db')
    try:
        instance, service = runtime(db, bot=Bot(reply=answer, error=error))
        if error:
            with pytest.raises(RuntimeError, match='Command processing failed'):
                asyncio.run(Runtime.handle_room_post(instance, ROOM, post(), rx()))
        else:
            asyncio.run(Runtime.handle_room_post(instance, ROOM, post(), rx()))
        row, = entries(db)
        assert row['command_status'] == status and row['reply'] == ''
        assert service.posts == []
    finally:
        db.close()


def test_room_post_failure_saves_only_accepted_reply_parts(tmp_path):
    db = database(tmp_path / 'station.db')
    try:
        service = Service(fail_after=1)
        instance, _ = runtime(db, bot=Bot(reply='x' * 121), service=service)
        with pytest.raises(RuntimeError, match='Room post failed'):
            asyncio.run(Runtime.handle_room_post(instance, ROOM, post(), rx()))
        row, = entries(db)
        assert service.posts == ['x' * 120]
        assert row['reply'] == 'x' * 120
        assert row['command_status'] == 'partial'
    finally:
        db.close()


def test_existing_history_migrates_without_losing_rows(tmp_path):
    path = tmp_path / 'old.db'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE logger (id INTEGER PRIMARY KEY, recv_time INTEGER)')
    conn.execute('INSERT INTO logger (recv_time) VALUES (123)')
    conn.commit()
    conn.close()
    db = database(path)
    try:
        columns = {row['name'] for row in db.db.execute('PRAGMA table_info(logger)')}
        assert {'room_id', 'command_status'} <= columns
        assert db.db.execute('SELECT recv_time FROM logger WHERE id=1').fetchone()[0] == 123
        db.create_database()  # migration is idempotent
    finally:
        db.close()
