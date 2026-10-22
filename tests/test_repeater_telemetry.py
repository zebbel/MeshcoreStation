"""Optional temperature extends the existing monitor without more radio traffic."""
import asyncio
import logging
import sqlite3
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from flask import Flask, request
from meshcore import EventType
from meshcorestation.storage import voltage_store as store, passive_stats
from meshcorestation.radio.voltage_monitor import VoltageMonitor
from meshcorestation.web import voltage_api
from meshcorestation import battery_templates

KEY='ab'*32


def station():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE repeaters(public_key TEXT,name TEXT,adv_type INTEGER,latitude REAL,longitude REAL)')
    db.execute('INSERT INTO repeaters VALUES(?,\'Hill\',2,49,8)',(KEY,))
    store.initialize(db);store.ensure_repeater(db,KEY);db.commit()
    return db


def test_migration_preserves_battery_records_templates_schedules_and_pending_reads():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.executescript('''
      CREATE TABLE voltage_config(id INTEGER PRIMARY KEY CHECK(id=1),public_key TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,interval_minutes INTEGER DEFAULT 45,reports_enabled INTEGER DEFAULT 1,
        report_time_1 TEXT DEFAULT '09:15',report_time_2 TEXT DEFAULT '21:15',timezone TEXT DEFAULT 'UTC',
        voltage_channel INTEGER DEFAULT 4,report_target TEXT DEFAULT 'room:2',report_template TEXT DEFAULT 'Custom {reading}',
        revision INTEGER DEFAULT 7,updated_at REAL DEFAULT 123,request_seq INTEGER DEFAULT 3,handled_seq INTEGER DEFAULT 2);
      INSERT INTO voltage_config(id) VALUES(1);
      CREATE TABLE voltage_samples(id INTEGER PRIMARY KEY,public_key TEXT NOT NULL,name TEXT NOT NULL,
        sampled_at REAL NOT NULL,voltage REAL,error TEXT,voltage_channel INTEGER NOT NULL,interval_seconds INTEGER NOT NULL);
    ''')
    db.execute('UPDATE voltage_config SET public_key=?',(KEY,))
    db.execute("INSERT INTO voltage_samples VALUES(42,?,'Old hill',1000,3.92,NULL,4,2700)",(KEY,));db.commit()
    before=dict(db.execute('SELECT * FROM voltage_config').fetchone())
    store.initialize(db);store.initialize(db)
    after=store.config(db,KEY)
    for field,value in before.items():assert after[field]==value
    row=dict(db.execute('SELECT * FROM voltage_samples WHERE id=42').fetchone())
    assert row['voltage']==3.92 and row['sampled_at']==1000
    assert row['temperature'] is None and row['temperature_channel'] is None and row['temperature_error'] is None
    assert after['temperature_channel']==1 and store.latest_temperature(db,after) is None
    assert db.execute('SELECT COUNT(*) FROM voltage_samples').fetchone()[0]==1
    db.close()


@pytest.mark.parametrize('value',[0,-12.5,24.6,100])
def test_temperature_accepts_zero_negative_and_celsius(value):
    assert store.extract_temperature([{'type':'temperature','channel':0,'value':value}],0)==value


@pytest.mark.parametrize('records',[
 [],[{'type':'temperature','channel':2,'value':20}],
 [{'type':'temperature','channel':1,'value':value} for value in (1,2)],
 *[[{'type':'temperature','channel':1,'value':value}] for value in (True,None,'24.6',float('nan'),float('inf'),-300,1001)]])
def test_temperature_missing_ambiguous_or_invalid_is_not_zero(records):
    with pytest.raises(ValueError):store.extract_temperature(records,1)


@pytest.mark.parametrize('voltage,temperature,expect_v,expect_t',[
 (3.92,24.6,3.92,24.6),(3.92,None,3.92,None),(None,-5,None,-5),(3.92,0,3.92,0),
 (3.92,False,3.92,None),(None,None,None,None)])
def test_single_telemetry_exchange_saves_sensors_independently(voltage,temperature,expect_v,expect_t):
    db=station();cfg=store.config(db,KEY)
    payload=[]
    if voltage is not None:payload.append({'type':'voltage','channel':1,'value':voltage})
    if temperature is not None:payload.append({'type':'temperature','channel':1,'value':temperature})
    contact={'public_key':KEY,'type':2}
    commands=NS(get_contacts=AsyncMock(return_value=NS(type=EventType.CONTACTS,payload={KEY:contact})),
        send_login_sync=AsyncMock(return_value=NS(type=EventType.LOGIN_SUCCESS,payload={'pubkey_prefix':KEY[:12]})),
        req_telemetry_sync=AsyncMock(return_value=payload))
    monitor=VoltageMonitor(NS(database=NS(db=db),mc=NS(commands=commands),logger=logging.getLogger('test')))
    result=asyncio.run(monitor.sample(cfg))
    commands.req_telemetry_sync.assert_awaited_once()
    commands.send_login_sync.assert_awaited_once()
    assert result['voltage']==expect_v and result['temperature']==expect_t
    assert bool(result['error'])==(expect_v is None)
    assert bool(result['temperature_error'])==(expect_t is None)
    assert result['temperature_channel']==1 and result['sampled_at']>0
    assert store.latest_temperature(db,cfg)['id']==result['id']
    if expect_v is not None:assert store.latest_reading(db,cfg)['id']==result['id']
    db.close()


def test_channel_validation_and_older_clients_keep_current_settings():
    db=station()
    db.execute('UPDATE voltage_config SET temperature_channel=4 WHERE public_key=?',(KEY,));db.commit()
    cfg=store.config(db,KEY);value={field:cfg[field] for field in store.FIELDS}
    for invalid in (True,1.5,-1,256,'1',None):
        with pytest.raises(ValueError):store.validate({**value,'temperature_channel':invalid},db)
    assert store.validate({**value,'temperature_channel':0},db)['temperature_channel']==0
    del value['temperature_channel'];del value['report_template']
    assert store.validate(value,db)['temperature_channel']==4
    db.close()


def test_history_periods_filter_temperature_channel_independently_of_voltage(tmp_path,monkeypatch):
    path=tmp_path/'station.db';db=station();disk=sqlite3.connect(path);db.backup(disk);disk.close();db.close()
    monkeypatch.setattr(voltage_api,'DB_PATH',path);monkeypatch.setattr(voltage_api,'DATA_DIR',tmp_path)
    monkeypatch.setattr(passive_stats,'STATS_PATH',tmp_path/'stats.db');passive_stats.initialize()
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE bot_settings(id INTEGER PRIMARY KEY,channel_name TEXT)')
        db.execute("INSERT INTO bot_settings VALUES(1,'Ops')")
        now=time.time()
        for days,voltage_channel,temp_channel,temp in [(0,1,1,24.6),(2,1,1,20),(8,1,1,10),(31,1,1,8),(.1,2,1,0),(.2,1,2,99)]:
            db.execute('INSERT INTO voltage_samples(public_key,name,sampled_at,voltage,voltage_channel,interval_seconds,temperature,temperature_channel) VALUES(?,?,?,?,?,?,?,?)',
                       (KEY,'Hill',now-days*86400,3.92,voltage_channel,1800,temp,temp_channel))
    app=Flask(__name__);app.add_url_rule('/voltage',view_func=lambda:voltage_api.voltage_request(request),methods=['GET','POST'])
    client=app.test_client()
    for days,values in [(1,[0,24.6]),(7,[20,0,24.6]),(30,[10,20,0,24.6])]:
        response=client.get(f'/voltage?public_key={KEY}&days={days}')
        assert response.status_code==200
        data=response.json
        assert [row['temperature'] for row in data['temperature_samples']]==values
        assert data['latest_temperature']['temperature']==24.6
        assert all(row['voltage_channel']==1 for row in data['samples'])
        assert all(row['temperature_channel']==1 for row in data['temperature_samples'])
    cfg=data['config'];value={field:cfg[field] for field in store.FIELDS};value['temperature_channel']=0
    result=client.post('/voltage',json={'operation':'save','public_key':KEY,'expected_revision':cfg['revision'],'value':value})
    assert result.status_code==200 and result.json['config']['temperature_channel']==0


def test_temperature_placeholder_is_optional_and_uses_same_reading_channel():
    sample={'name':'Hill','sampled_at':1000,'voltage':3.92,'temperature':24.6,'temperature_channel':3}
    cfg={'public_key':KEY,'timezone':'UTC','temperature_channel':3}
    assert battery_templates.render('{repeater_temperature} °C',sample,cfg)=='24.6 °C'
    assert battery_templates.render('{repeater_temperature:.2f}',sample,cfg)=='24.60'
    assert battery_templates.render('{repeater_temperature}',sample,{**cfg,'temperature_channel':1})=='unknown'
    assert battery_templates.render('{repeater_temperature}',{**sample,'temperature':None},cfg)=='unknown'
    assert battery_templates.render(battery_templates.DEFAULT,sample,cfg).startswith('Battery Hill: 3.92 V | ')
    assert battery_templates.preview('{repeater_temperature} °C')=='24.6 °C'
    assert any(item['name']=='repeater_temperature' and item['numeric'] for item in battery_templates.catalog())
