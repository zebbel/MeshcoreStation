import json
import sqlite3
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import asyncio
import pytest
from flask import Flask
from meshcorestation.storage import oled_store as store, database
from meshcorestation.storage.voltage_store import initialize
from meshcorestation.radio.oled_scene import render
from meshcorestation.radio.oled import OledDisplay


@pytest.fixture
def db(tmp_path,monkeypatch):
    path=tmp_path/'station.db'
    monkeypatch.setattr(database,'DB_FILE',path)
    instance=database.Database(NS(info=lambda *args:None))
    initialize(instance.db)
    instance.db.execute("INSERT INTO repeaters (public_key,name,first_seen,last_seen) VALUES ('abc','Test repeater',1,1)")
    instance.db.execute("UPDATE voltage_config SET public_key='abc'")
    instance.db.execute("INSERT INTO logger (recv_time,sender,message,rssi,snr,path_len) VALUES (100000,'Alice','ping',-95,7,2)")
    instance.db.execute("INSERT INTO voltage_samples (public_key,name,sampled_at,voltage,voltage_channel,interval_seconds) VALUES ('abc','Test',100000,3.6,1,1800)")
    instance.db.commit()
    yield instance.db,path
    instance.close()


def test_defaults_render_and_conflict(db):
    conn,_=db
    pages=store.validate(store.defaults())
    drawing=render(conn,pages[0],100001)
    assert any('3.60V' in t[-1] for t in drawing['texts'])
    assert all(len(t[-1])<=21 and t[0]+len(t[-1])*6*t[2]<=128 for t in drawing['texts'])
    snap=store.snapshot(conn)
    pages[0]['name']='Custom'
    with conn: result=store.save(conn,pages,snap['revision'])
    assert result['revision']!=snap['revision']
    with pytest.raises(RuntimeError):
        with conn: store.save(conn,pages,snap['revision'])
    assert store.snapshot(conn)['pages'][0]['name']=='Custom'


@pytest.mark.parametrize('mutation',[
    lambda p:p[0]['elements'][0].update(x=127),
    lambda p:p[0]['elements'][3].update(minimum=5,maximum=3),
    lambda p:p[0]['elements'][3].update(maximum=float('nan')),
    lambda p:p[0]['elements'][3].update(source='secret; DROP TABLE logger'),
    lambda p:p[0]['elements'][0].update(size=3),
    lambda p:[x.update(enabled=False) for x in p],
])
def test_invalid_documents(mutation):
    pages=store.defaults();mutation(pages)
    with pytest.raises(ValueError):store.validate(pages)


def test_graph_bounds_budget_and_selected_source(db):
    conn,_=db
    for i in range(500):
        conn.execute("INSERT INTO voltage_samples (public_key,name,sampled_at,voltage,voltage_channel,interval_seconds) VALUES ('abc','Test',?,?,1,1800)",(100002+i*100,2.5+i/200))
    p=dict(name='Graphs',enabled=True,elements=[
        store.element('graph',0,0,128,64,source='battery.voltage',hours=24,minimum=3,maximum=4.2)
        for _ in range(4)])
    drawing=render(conn,store.validate([p])[0],150000)
    assert len(drawing['lines'])<=256
    assert all(0<=v< (128 if i%2==0 else 64) for line in drawing['lines'] for i,v in enumerate(line))
    conn.execute("UPDATE voltage_config SET public_key='other'")
    assert len(render(conn,p,150000)['lines'])==8  # axes only, no unrelated battery data


def test_api_guards_preview_save_and_expiry(db,monkeypatch):
    from meshcorestation.web import oled_api
    from meshcorestation.bridge import bridge
    conn,path=db
    monkeypatch.setattr(oled_api,'DB_PATH',path)
    app=Flask(__name__);oled_api.register_oled_routes(app);client=app.test_client()
    headers={'X-Meshcore-Control':'1'}
    assert client.get('/api/oled/pages').status_code==403
    assert client.get('/api/oled/pages',headers={**headers,'Origin':'https://evil.test'}).status_code==403
    monkeypatch.setattr(bridge,'runtime',NS(
        companion=NS(mc=NS(connection_manager=NS(is_connected=True))),
        oled=NS(task=NS(done=lambda:False),acquired=True,compatible=True)))
    original=client.get('/api/oled/pages',headers=headers).json
    pages=original['pages'];pages[0]['name']='Draft'
    assert client.post('/api/oled/pages',headers=headers,json={'action':'preview','pages':pages}).json['drawing']
    assert store.snapshot(conn)['pages'][0]['name']=='Battery'
    monkeypatch.setattr(bridge,'runtime',NS(companion=NS(mc=NS(connection_manager=NS(is_connected=True))),oled=NS(task=NS(done=lambda:False),acquired=True,compatible=True)))
    assert client.post('/api/oled/pages',headers=headers,json={'action':'device_preview','pages':pages}).status_code==200
    assert store.active(conn,0)[0]['name']=='Draft'
    assert store.active(conn,1e12)[0]['name']=='Battery'
    assert client.post('/api/oled/pages',headers=headers,json={'action':'stop_preview'}).status_code==200
    assert client.post('/api/oled/pages',headers=headers,json={'action':'save','pages':pages,'revision':original['revision']}).status_code==200
    assert client.post('/api/oled/pages',headers=headers,json={'action':'save','pages':pages,'revision':original['revision']}).status_code==409


def test_runtime_uses_saved_pages_font_size_and_cycles(db):
    conn,_=db
    pages=[dict(name=str(i),enabled=i!=1,elements=[store.element('text',2,4,120,16,size=2,text='Page '+str(i))]) for i in range(4)]
    with conn:store.save(conn,pages,store.snapshot(conn)['revision'])
    display=OledDisplay(NS(database=NS(db=conn)))
    display.transport=NS(command=AsyncMock());display.buttons=True
    async def scenario():
        await display.draw((7,256,83))
        assert display.page_count==3
        display.on_button(1)
        await display.draw((7,256,83))
        calls=[c.args for c in display.transport.command.await_args_list]
        assert (2,b'\x02\x04\x02Page 2') in calls
        display.on_button(1);display.on_button(1)
        assert display.page==0
    asyncio.run(scenario())


def test_incompatible_companion_blocks_all_editor_operations(db,monkeypatch):
    from meshcorestation.web import oled_api
    from meshcorestation.bridge import bridge
    _,path=db
    monkeypatch.setattr(oled_api,'DB_PATH',path)
    monkeypatch.setattr(bridge,'runtime',None)
    app=Flask(__name__);oled_api.register_oled_routes(app);client=app.test_client()
    headers={'X-Meshcore-Control':'1'}
    assert client.get('/api/oled/pages?status=1',headers=headers).json['compatible'] is False
    assert client.get('/api/oled/pages',headers=headers).status_code==409
    for action in ('preview','device_preview','save'):
        assert client.post('/api/oled/pages',headers=headers,json={'action':action,'pages':store.defaults()}).status_code==409


def test_failed_battery_read_uses_marked_last_success(db):
    conn,_=db
    conn.execute("INSERT INTO voltage_samples (public_key,name,sampled_at,voltage,error,voltage_channel,interval_seconds) VALUES ('abc','Test',100060,NULL,'timeout',1,1800)")
    drawing=render(conn,store.defaults()[0],100120)
    assert '*3.60V' in [t[-1] for t in drawing['texts']]
    assert any('Latest read failed' in w and '2 minutes' in w for w in drawing['warnings'])
    conn.execute("UPDATE voltage_config SET voltage_channel=2")
    drawing=render(conn,store.defaults()[0],100120)
    assert '--V' in [t[-1] for t in drawing['texts']]
    assert not any('*3.60V' == t[-1] for t in drawing['texts'])


def test_old_battery_read_age_and_recovery(db):
    conn,_=db
    page={'elements':[store.element('value',0,0,128,8,source='battery.age_minutes',size=1,label='',units='m',precision=0)]}
    assert render(conn,page,100120)['texts'][0][-1]=='2m'
    assert render(conn,store.defaults()[0],104000)['warnings']
    conn.execute("INSERT INTO voltage_samples (public_key,name,sampled_at,voltage,voltage_channel,interval_seconds) VALUES ('abc','Test',104001,3.8,1,1800)")
    drawing=render(conn,store.defaults()[0],104002)
    assert '3.80V' in [t[-1] for t in drawing['texts']]
    assert drawing['warnings']==[]


def test_rotation_migration_and_revision(db):
    conn, _ = db
    initial = store.snapshot(conn)
    assert initial['rotation'] == dict(enabled=False, page_seconds=10, button_seconds=30)
    settings = dict(enabled=True, page_seconds=5, button_seconds=45)
    with conn:
        saved = store.save(conn, initial['pages'], initial['revision'], settings)
    assert saved['rotation'] == settings
    assert saved['revision'] != initial['revision']
    with pytest.raises(RuntimeError):
        with conn:
            store.save(conn, initial['pages'], initial['revision'], settings)
    store.initialize(conn)
    assert store.snapshot(conn)['rotation'] == settings


@pytest.mark.parametrize('key,value', [('enabled', 1), ('page_seconds', 0),
    ('page_seconds', 1.5), ('button_seconds', 3601), ('button_seconds', True)])
def test_rotation_validation(key, value):
    settings = store.rotation_defaults()
    settings[key] = value
    with pytest.raises(ValueError):
        store.validate_rotation(settings)


def test_auto_rotation_button_hold_preview_and_disable(monkeypatch):
    display = OledDisplay(NS())
    settings = dict(enabled=True, page_seconds=5, button_seconds=30)
    display.rotate(settings, 3, False, 100)
    display.rotate(settings, 3, False, 104)
    assert display.page == 0
    display.rotate(settings, 3, False, 105)
    assert display.page == 1
    display.buttons = True
    monkeypatch.setattr('meshcorestation.radio.oled.time.monotonic', lambda: 107)
    display.on_button(1)
    assert display.page == 2 and display.rotate_at == 137
    display.rotate(settings, 3, False, 136)
    assert display.page == 2
    monkeypatch.setattr('meshcorestation.radio.oled.time.monotonic', lambda: 136)
    display.on_button(1)
    assert display.page == 0 and display.rotate_at == 166
    display.rotate(settings, 3, False, 166)
    assert display.page == 1
    display.rotate(settings, 3, True, 167)
    display.rotate(settings, 3, True, 200)
    assert display.page == 1 and display.rotate_at is None
    display.rotate(settings, 3, False, 201)
    assert display.page == 1 and display.rotate_at == 206
    display.rotate({**settings, 'enabled': False}, 3, False, 210)
    assert display.page == 1 and display.rotate_at is None
    display.rotate(settings, 1, False, 220)
    assert display.page == 0 and display.rotate_at is None


def test_rotation_old_database_migration():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE oled_pages (id INTEGER PRIMARY KEY, document TEXT NOT NULL, preview TEXT, preview_until REAL DEFAULT 0)')
    pages = store.defaults()
    pages[0]['name'] = 'Keep me'
    conn.execute('INSERT INTO oled_pages(id,document) VALUES(1,?)', (json.dumps(pages),))
    store.initialize(conn)
    assert store.snapshot(conn)['pages'][0]['name'] == 'Keep me'
    assert store.snapshot(conn)['rotation']['enabled'] is False
    conn.close()


@pytest.mark.parametrize('flags,wire_size', [(15,3),(7,1)])
def test_medium_metrics_and_firmware_fallback(db, flags, wire_size):
    conn,_ = db
    page = dict(name='Medium',enabled=True,elements=[store.element('text',0,52,128,12,text='ABCDEFGHIJKLMNOPQ',size=3)])
    store.validate([page])
    drawing = render(conn,page,100001)
    assert drawing['texts'] == [(0,52,3,'ABCDEFGHIJKLMNOP')]
    with conn:
        store.save(conn,[page],store.snapshot(conn)['revision'])
    display = OledDisplay(NS(database=NS(db=conn)))
    display.transport = NS(command=AsyncMock())
    asyncio.run(display.draw((flags,256,83)))
    texts = [c.args[1] for c in display.transport.command.await_args_list if c.args[0]==2]
    assert texts == [bytes([0,52,wire_size])+b'ABCDEFGHIJKLMNOP']
    page['elements'][0]['h'] = 11
    with pytest.raises(ValueError):
        store.validate([page])
