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
    original=client.get('/api/oled/pages',headers=headers).json
    pages=original['pages'];pages[0]['name']='Draft'
    assert client.post('/api/oled/pages',headers=headers,json={'action':'preview','pages':pages}).json['drawing']
    assert store.snapshot(conn)['pages'][0]['name']=='Battery'
    monkeypatch.setattr(bridge,'runtime',NS(oled=NS(task=NS(done=lambda:False),acquired=True)))
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
