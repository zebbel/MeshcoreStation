from unittest.mock import Mock

from flask import Flask
import pytest

from meshcorestation.web import update_api


@pytest.mark.parametrize(('installed', 'other'), [('V5', 'V6'), ('V6', 'V5')])
def test_dashboard_can_switch_without_opening_other_branches(monkeypatch, installed, other):
    updater = update_api.updater
    monkeypatch.setattr(updater, 'local_branch', lambda: installed)
    monkeypatch.setattr(updater, 'local_revision', lambda: 'a' * 40)
    check = Mock(return_value={'available': True, 'branch': other, 'latest': 'b' * 40})
    queue = Mock()
    monkeypatch.setattr(updater, 'check', check)
    monkeypatch.setattr(updater, 'queue', queue)
    app = Flask(__name__)
    update_api.register_update_routes(app)
    client = app.test_client()

    def request(action, **fields):
        return client.post('/api/update', json={'action': action, **fields},
                           headers={'X-Meshcore-Control': '1'})

    assert request('branches').json['branches'] == {'V5': 'V5', 'V6': 'V6'}
    assert request('check').status_code == 200
    check.assert_called_with(installed)
    assert request('check', branch=other).json['check']['available']
    check.assert_called_with(other)
    assert request('install', branch=other, target='b' * 40).status_code == 200
    queue.assert_called_once_with('b' * 40, other)

    for invalid in ('main', 'V4', None, []):
        assert request('check', branch=invalid).status_code == 409
        assert request('install', branch=invalid, target='b' * 40).status_code == 409
    assert check.call_count == 2
    assert queue.call_count == 1
    assert client.post('/api/update', json={'action': 'install', 'branch': 'V6'}).status_code == 403
