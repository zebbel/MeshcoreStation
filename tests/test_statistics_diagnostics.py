import json
from pathlib import Path
import sqlite3
from scripts.benchmark_statistics import create_fixture,KEY
from scripts import diagnose_statistics as diagnose
from meshcorestation.storage import statistics_view


def test_live_profile_redacted_and_source_preserved(tmp_path):
    path=create_fixture(tmp_path,2500)
    # Move synthetic timestamps into the real current 24h window.
    import time
    from meshcorestation.storage.passive_stats import statistics_path
    with sqlite3.connect(statistics_path(path,KEY)) as db:db.execute('UPDATE observations SET received_at=?',(time.time()-1,))
    before=statistics_path(path,KEY).read_bytes()
    original=statistics_view._spool
    value=diagnose.inspect(path)
    assert value['window']['rows']==2500 and value['profile']['error'] is None
    assert value['profile']['fetched_rows']==2500 and value['profile']['parsed_routes']<=512
    assert {'source_fetch','scope_matching','route_resolution','scratch_insert','space_checks'}<=value['profile']['breakdown_ms'].keys()
    assert statistics_view._spool is original
    assert statistics_path(path,KEY).read_bytes()==before
    output=json.dumps(value)
    assert 'Synthetic ' not in output and 'scope_key' not in output and 'pkt_payload' not in output


def test_timeout_restores_instrumentation(tmp_path,monkeypatch):
    path=create_fixture(tmp_path,2500);original=statistics_view.RouteCache.get
    monkeypatch.setattr(statistics_view,'QUERY_BUDGET_SECONDS',0)
    value=diagnose.profile_actual(path,KEY,1)
    assert value['error']==dict(type='QueryTimeout',stage='metadata')
    assert statistics_view.RouteCache.get is original


def test_env_data_path_is_parsed_without_shell_execution(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.delenv('MESHCORESTATION_DATA_DIR',raising=False)
    value=str(tmp_path/'literal $(do-not-execute) data')
    Path('meshcorestation.env').write_text('MESHCORESTATION_DATA_DIR="'+value+'"\nUNRELATED_SECRET=unused\n')
    diagnose.environment_data_directory()
    import os
    assert os.environ['MESHCORESTATION_DATA_DIR']==value
    monkeypatch.delenv('MESHCORESTATION_DATA_DIR')
