"""Battery report destinations stay independent of the selected bot chat."""
import asyncio
import sqlite3
import time
from types import SimpleNamespace

import pytest
from meshcore import EventType
from meshcorestation.radio.voltage_monitor import VoltageMonitor
from meshcorestation.storage.voltage_store import FIELDS, config, initialize, validate

KEY = 'ab' * 32
SAMPLE = {'name': 'Field repeater', 'sampled_at': time.time(), 'voltage': 3.92}

def database():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE repeaters(public_key TEXT, adv_type INTEGER)')
    db.execute('INSERT INTO repeaters VALUES (?, 2)', (KEY,))
    initialize(db)
    db.execute('INSERT INTO voltage_reports(slot,public_key,due_at,attempted_at,status,detail) VALUES (?,?,?,?,?,?)',
               ('morning',KEY,time.time(),time.time(),'unconfirmed','pending'))
    db.commit()
    return db

class Service:
    def __init__(self, enabled=True):
        self.enabled, self.posts = enabled, []
    def config(self, rid):
        assert rid == 2
        return {'name':'Test room','enabled':self.enabled}
    def local_post(self, rid, text):
        self.posts.append((rid,text))

class Commands:
    def __init__(self):
        self.sent = []
        self.scope_resets = []
    async def set_flood_scope(self, value):
        self.scope_resets.append(value)
        return SimpleNamespace(type=EventType.OK)
    async def send_chan_msg(self, index, message):
        self.sent.append((index,message))
        return SimpleNamespace(type=EventType.OK)

def monitor(db, room_bot=None, enabled=True, running=True):
    service, commands = Service(enabled), Commands()
    worker = SimpleNamespace(service=service,status=lambda:{'running':running})
    companion = SimpleNamespace(database=SimpleNamespace(db=db),room_bot_id=room_bot,room_worker=worker,
        channel_name='Ops',channel_idx=1,channel_hash=__import__('hashlib').sha256(b'\x11'*16).digest()[:1].hex(),
        mc=SimpleNamespace(commands=commands),reply_lock=asyncio.Lock(),
        logger=SimpleNamespace(info=lambda *a:None))
    return VoltageMonitor(companion), service, commands

def cfg(db,target):
    with db:
        db.execute('UPDATE voltage_config SET report_target=? WHERE id=1',(target,))
    return config(db)

def report(db):
    return dict(db.execute("SELECT * FROM voltage_reports WHERE slot='morning'").fetchone())

def test_migration_retains_bot_destination():
    db=sqlite3.connect(':memory:')
    db.row_factory=sqlite3.Row
    db.executescript("""
      CREATE TABLE voltage_config(
        id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 0,
        public_key TEXT DEFAULT '', interval_minutes INTEGER DEFAULT 30,
        reports_enabled INTEGER DEFAULT 1, report_time_1 TEXT DEFAULT '08:00',
        report_time_2 TEXT DEFAULT '20:00', timezone TEXT DEFAULT 'Europe/Berlin',
        voltage_channel INTEGER DEFAULT 1, revision INTEGER DEFAULT 0,
        updated_at REAL DEFAULT 0, request_seq INTEGER DEFAULT 0,
        handled_seq INTEGER DEFAULT 0);
      INSERT INTO voltage_config(id) VALUES(1);
    """)
    initialize(db)
    assert config(db)['report_target']=='bot'
    initialize(db)
    assert sum(r['name']=='report_target' for r in db.execute('PRAGMA table_info(voltage_config)'))==1
    assert db.execute('SELECT COUNT(*) FROM voltage_config').fetchone()[0]==1
    db.close()

def test_destination_validation():
    db=database()
    value={field:config(db)[field] for field in FIELDS}
    for target in ('bot','room:2','channel:Ops'):
        assert validate(dict(value,report_target=target),db)['report_target']==target
    for target in ('room:0','room:-2','room:abc','channel:','channel:\n','bogus',None):
        with pytest.raises(ValueError):
            validate(dict(value,report_target=target),db)
    db.close()

def test_room_report_not_sent_to_channel():
    db=database()
    m,s,c=monitor(db)
    asyncio.run(m.report('morning',cfg(db,'room:2'),SAMPLE))
    assert s.posts and not c.sent
    assert report(db)['channel_name']=='Room: Test room'
    assert report(db)['status']=='queued'
    db.close()

def test_bot_follow_room_and_offline_room():
    db=database()
    m,s,c=monitor(db,room_bot=2)
    asyncio.run(m.report('morning',cfg(db,'bot'),SAMPLE))
    assert s.posts and not c.sent
    db.close()
    db=database()
    m,s,c=monitor(db,running=False)
    asyncio.run(m.report('morning',cfg(db,'room:2'),SAMPLE))
    assert not s.posts and report(db)['status']=='failed'
    db.close()

def test_explicit_channel_independent_of_bot_room(monkeypatch):
    async def channels(companion):
        return {'channels':[{'index':3,'name':'Battery ops','type':'private'}]}, [('',bytes(16))]*3+[('Battery ops',b'\x22'*16)]
    monkeypatch.setattr('meshcorestation.radio.channels_control.read_channels',channels)
    db=database()
    m,s,c=monitor(db,room_bot=2)
    asyncio.run(m.report('morning',cfg(db,'channel:Battery ops'),SAMPLE))
    assert not s.posts and c.sent and c.sent[0][0]==3
    assert c.scope_resets==[None]
    assert report(db)['channel_name']=='Chat: Battery ops'
    db.close()
