import base64
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

import pytest
from flask import Flask
from meshcorestation.web.companion_share import contact_card
from meshcorestation.web import companion_settings


def test_contact_url_and_svg():
    result = contact_card({'name': 'Station & ö', 'public_key': 'AB' * 32})
    assert parse_qs(urlsplit(result['uri']).query) == {
        'name': ['Station & ö'], 'public_key': ['ab' * 32], 'type': ['1']}
    root = ElementTree.fromstring(base64.b64decode(result['image'].split(',')[1]))
    assert root.tag.endswith('svg')
    assert root.find('{http://www.w3.org/2000/svg}path') is not None


def test_invalid_key():
    with pytest.raises(ValueError):
        contact_card({'name': 'Station', 'public_key': 'bad'})


def test_share_reads_live_settings_and_is_guarded(monkeypatch):
    app = Flask(__name__)
    companion_settings.register_companion_routes(app)
    calls = []
    def read(payload):
        calls.append(payload)
        return {'ok': True, 'settings': {'name': 'Station', 'public_key': 'ab' * 32}}
    monkeypatch.setattr(companion_settings, 'bot_request', read)
    client = app.test_client()
    assert client.get('/api/companion/share').status_code == 403
    assert not calls
    result = client.get('/api/companion/share', headers={'X-Meshcore-Control': '1'})
    assert result.status_code == 200
    assert result.json['uri'].startswith('meshcore://contact/add?')
    assert calls == [{'operation': 'get'}]
    assert result.headers['Cache-Control'] == 'no-store'
    assert client.post('/api/companion/share').status_code == 405
