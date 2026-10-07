"""Offline installation check; never opens a serial device or sends a message."""
import tempfile
from pathlib import Path
from markupsafe import escape
from Crypto.Cipher import AES
import dbus_fast
from meshcorestation.storage import database
from meshcorestation.storage.voltage_store import initialize
from meshcorestation.web.app import create_app


class QuietLogger:
    def info(self, *args):
        pass


def main():
    assert str(escape('<test>&')) == '&lt;test&gt;&amp;'
    key = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
    plain = bytes.fromhex('00112233445566778899aabbccddeeff')
    assert AES.new(key, AES.MODE_ECB).encrypt(plain).hex() == '69c4e0d86a7b0430d8cdb78070b4c55a'
    with tempfile.TemporaryDirectory() as directory:
        database.DB_FILE = Path(directory) / 'check.db'
        db = database.Database(QuietLogger())
        try:
            initialize(db.db)
            assert db.get_bot_settings()['channel_name'] == ''
        finally:
            db.close()
    app = create_app()
    required = {'/api/update', '/api/update/health', '/api/bot/commands', '/api/repeater', '/api/bot/runtime', '/api/bot/voltage', '/api/companion', '/api/companion/contacts', '/api/companion/channels'}
    assert required <= {route.rule for route in app.server.url_map.iter_rules()}
    assert app.server.test_client().get('/').status_code == 200
    print('MeshcoreStation imports, native dependencies, fresh database and dashboard routes OK.')


if __name__ == '__main__':
    main()
