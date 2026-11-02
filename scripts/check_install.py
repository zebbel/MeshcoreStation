"""V5 fresh-install smoke check: isolated databases, no serial device or network."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    code='''
from pathlib import Path
from meshcorestation.config import DATA_DIR,DB_PATH
from meshcorestation.web.app import create_app
from meshcorestation import __version__
import sqlite3
app=create_app();client=app.server.test_client()
assert __version__=='5.2.0'
assert {p.name for p in DATA_DIR.glob('*.db')}=={'meshcorestation.db','knownRepeaters.db'}
with sqlite3.connect(DB_PATH) as db:
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'repeaters' not in tables
assert client.get('/').status_code==200
assert client.get('/_dash-layout').status_code==200
assert client.get('/api/repeater-statistics/status').status_code==200
assert client.get('/api/repeater-statistics/view').status_code==200
assert not (DATA_DIR/'repeaterStatistics').exists()
rules={r.rule for r in app.server.url_map.iter_rules()}
assert {'/api/bot/commands','/api/bot/scopes','/api/repeater','/api/bot/voltage','/api/companion/contacts','/api/companion/channels','/api/update','/api/maps/repeaters','/api/replies/<int:command_id>','/api/repeater-statistics/status'}<=rules
assert not {'/api/repeater-performance','/api/repeater-network','/api/repeater-statistics','/api/rooms'}&rules
print('V5 5.2.0: fresh two-database ownership, imports, dashboard and included routes OK; no radio opened.')
'''
    with tempfile.TemporaryDirectory(prefix='v5-install-check-',dir=os.getenv('TMPDIR',str(Path.cwd()))) as directory:
        subprocess.run([sys.executable,'-c',code],env={**os.environ,'MESHCORESTATION_DATA_DIR':directory},check=True)


if __name__=='__main__':main()
