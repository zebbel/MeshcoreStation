import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from flask import Flask
from meshcorestation import battery_templates as t
from meshcorestation.storage import voltage_store as store
from meshcorestation.web.voltage_api import register_battery_template_routes

KEY='ab'*32
SAMPLE={'name':'Hill','voltage':3.86,'sampled_at':datetime(2026,10,22,8,tzinfo=ZoneInfo('Europe/Berlin')).timestamp()}
CFG={'public_key':KEY,'timezone':'Europe/Berlin'}


def test_default_preserves_old_message_and_custom_uses_reading_time():
    assert t.render(t.DEFAULT,SAMPLE,CFG)=='Battery Hill: 3.86 V | 22.10 08:00'
    assert t.render('{repeater_name}: {battery_voltage:.1f}V ({battery_percent}%) {date} {time}',SAMPLE,CFG)=='Hill: 3.9V (52%) 22.10.2026 08:00:00'
    assert t.render('{{literal}} {repeater_name}',dict(SAMPLE,name='{battery_voltage}'),CFG)=='{literal} {battery_voltage}'
    assert 'unknown' in t.render('{battery_voltage}',dict(SAMPLE,voltage=None),CFG)


@pytest.mark.parametrize('text',['', '{name.__class__}', '{unknown}', '{battery_voltage!r}', '{battery_voltage:1000f}', '{reading:.2f}', '{reading', 'a\nb', 'x'*513])
def test_invalid_templates_rejected(text):
    with pytest.raises(ValueError):t.validate(text)


def test_upgrade_and_per_repeater_templates_preserve_schedule_and_destination():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE repeaters(public_key TEXT,adv_type INTEGER)')
    db.executemany('INSERT INTO repeaters VALUES(?,2)',[(KEY,),('cd'*32,)])
    store.initialize(db)
    first=store.ensure_repeater(db,KEY);second=store.ensure_repeater(db,'cd'*32)
    assert first['report_template']==second['report_template']==t.DEFAULT
    value={name:first[name] for name in store.FIELDS};value['report_template']='Custom {reading}'
    valid=store.validate(value,db)
    db.execute('UPDATE voltage_config SET report_template=? WHERE public_key=?',(valid['report_template'],KEY));db.commit()
    store.initialize(db)
    after=store.config(db,KEY)
    assert after['report_template']=='Custom {reading}'
    for field in ('report_time_1','report_time_2','report_target','timezone','interval_minutes'):
        assert after[field]==first[field]
    assert store.config(db,'cd'*32)['report_template']==t.DEFAULT
    del value['report_template']
    assert store.validate(value,db)['report_template']=='Custom {reading}'
    db.close()


def test_live_preview_uses_real_validation_without_radio():
    app=Flask(__name__);register_battery_template_routes(app);c=app.test_client();h={'X-Meshcore-Control':'1'}
    assert c.post('/api/battery-report-preview',json={'template':t.DEFAULT}).status_code==403
    result=c.post('/api/battery-report-preview',json={'template':'{reading}'},headers=h)
    assert result.status_code==200 and result.json['preview']=='3.86 V'
    assert c.post('/api/battery-report-preview',json={'template':'{bad}'},headers=h).status_code==400
