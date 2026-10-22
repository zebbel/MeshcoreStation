import json
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from flask import Flask
from meshcorestation import display
from meshcorestation.web.display_api import register_display_routes

@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setattr(display,'FILE',tmp_path/'display.json')
    app=Flask(__name__)
    register_display_routes(app)
    app.add_url_rule('/tool',view_func=lambda:'<html><head></head><body>Tool</body></html>')
    return app


def test_persistent_settings_and_default_format_do_not_change_timezones(app):
    zone=ZoneInfo('Europe/Berlin')
    stamp=datetime(2026,10,22,16,30,1,tzinfo=zone).timestamp()
    assert display.settings()=={'date_format':'german','hour_format':'24'}
    assert display.format_datetime(stamp)=='22.10.2026 16:30:01'
    display.save({'date_format':'us','hour_format':'12'})
    assert json.loads(display.FILE.read_text())==display.settings()
    assert display.format_datetime(stamp)=='10/22/2026 04:30:01 PM'
    assert display.format_datetime(stamp,ZoneInfo('UTC'))=='10/22/2026 02:30:01 PM'
    display.save({'date_format':'iso','hour_format':'24'})
    assert display.format_datetime(stamp)=='2026-10-22 16:30:01'
    assert display.format_datetime(stamp+3600*24*5)=='2026-10-27 15:30:01' # DST stays a timezone concern.


def test_display_api_is_shared_and_bootstraps_standalone_pages(app):
    c=app.test_client();headers={'X-Meshcore-Control':'1'}
    assert c.post('/api/display-settings',json={'date_format':'us','hour_format':'12'}).status_code==403
    assert c.post('/api/display-settings',json={'date_format':'us','hour_format':'12'},headers=headers).status_code==200
    assert c.get('/api/display-settings',headers=headers).json['settings']['date_format']=='us'
    html=c.get('/tool').text
    assert 'meshcorestation-display' in html and '/assets/aa_display.js' in html
    assert '&quot;date_format&quot;: &quot;us&quot;' in html
    assert c.post('/api/display-settings',json={'date_format':'us','hour_format':'12','timezone':'UTC'},headers=headers).status_code==400
    assert c.post('/api/display-settings',json={'date_format':'bad','hour_format':'24'},headers=headers).status_code==400
    assert display.settings()['date_format']=='us'
