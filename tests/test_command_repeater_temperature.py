"""Command temperature values come from saved telemetry, never a radio request."""
import asyncio
import sqlite3
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,Mock
import pytest
from flask import Flask,request
from meshcorestation.commands.context import collect
from meshcorestation.commands import templates
from meshcorestation.storage import voltage_store,command_store
from meshcorestation.web import commands_api

KEY='ab'*32
OTHER='cd'*32


@pytest.fixture
def db():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE repeaters(public_key TEXT,adv_type INTEGER)')
    db.executemany('INSERT INTO repeaters VALUES(?,2)',[(KEY,),(OTHER,)])
    voltage_store.initialize(db)
    yield db
    db.close()


def read(db,needed={'repeater_temperature'}):
    companion=NS(channel_name='Ops',_get_message_hops=lambda message:None,
        get_status=AsyncMock(),get_self_info=AsyncMock(),get_telemetry=AsyncMock())
    bot=NS(companion=companion,database=NS(db=db),logger=Mock())
    values=asyncio.run(collect(bot,needed,{'message':'temperature','name':'Alice'},None,[]))
    companion.get_status.assert_not_awaited();companion.get_self_info.assert_not_awaited();companion.get_telemetry.assert_not_awaited()
    return values


def sample(db,key,stamp,value,channel=3,error=None):
    db.execute('''INSERT INTO voltage_samples(public_key,name,sampled_at,voltage,error,voltage_channel,interval_seconds,
        temperature,temperature_channel,temperature_error) VALUES(?,?,?,NULL,'No voltage',1,1800,?,?,?)''',
        (key,'Hill',stamp,value,channel,error))


@pytest.mark.parametrize('value',[24.6,0,-5.2])
def test_default_repeater_and_configured_channel_use_latest_successful_temperature(db,value):
    voltage_store.ensure_repeater(db,KEY);voltage_store.ensure_repeater(db,OTHER)
    db.execute('UPDATE voltage_config SET temperature_channel=3 WHERE public_key=?',(KEY,))
    sample(db,KEY,1,10);sample(db,KEY,2,value)
    sample(db,KEY,3,None,error='No temperature');sample(db,KEY,4,99,channel=2)
    sample(db,OTHER,5,100)
    values=read(db)
    assert values['repeater_temperature']==value
    assert templates.render('{repeater_temperature} °C',values)==f'{value:.1f} °C'
    assert templates.render('{repeater_temperature:.2f}',values)==f'{value:.2f}'
    db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(KEY,))
    assert read(db)['repeater_temperature'] is None # Other uses its default channel 1, not 3.


def test_unknown_when_no_repeater_no_reading_or_no_telemetry_schema(db):
    assert templates.render('{repeater_temperature}',read(db))=='unknown'
    voltage_store.ensure_repeater(db,KEY)
    assert read(db)['repeater_temperature'] is None
    db.execute('DROP TABLE voltage_samples')
    assert read(db)['repeater_temperature'] is None


def test_unused_placeholder_does_not_read_telemetry_database():
    db=Mock();values=read(db,needed=set())
    assert 'repeater_temperature' not in values
    db.execute.assert_not_called()


def test_command_catalog_validation_preview_and_saved_reply(tmp_path,monkeypatch):
    path=tmp_path/'commands.db'
    with sqlite3.connect(path) as db:command_store.initialize(db)
    monkeypatch.setattr(commands_api,'DB_PATH',path)
    app=Flask(__name__);app.add_url_rule('/commands',view_func=lambda:commands_api.commands_request(request),methods=['GET','POST'])
    client=app.test_client();snapshot=client.get('/commands').json
    item=next(item for item in snapshot['placeholders'] if item['name']=='repeater_temperature')
    assert item['numeric'] and item['decimals']==1 and item['group']=='Repeater telemetry'
    commands=snapshot['commands']+[{'id':'temperature','trigger':'temperature','help':'Read saved repeater temperature','action':'reply','reply':'Temperature: {repeater_temperature:.1f} °C'}]
    preview=client.post('/commands',json={'operation':'preview','commands':commands,'selected_id':'temperature'})
    assert preview.status_code==200 and preview.json['reply']=='Temperature: 24.6 °C'
    saved=client.post('/commands',json={'operation':'save','commands':commands,'expected_revision':snapshot['revision']})
    assert saved.status_code==200
    assert next(command for command in saved.json['commands'] if command['id']=='temperature')['reply']=='Temperature: {repeater_temperature:.1f} °C'
