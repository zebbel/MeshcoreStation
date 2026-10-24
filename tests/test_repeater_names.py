import sqlite3
from meshcorestation.web import repeater_names


def test_known_directory_is_read_only_and_preserves_complete_keys(tmp_path, monkeypatch):
    path=tmp_path/'v3.db';key='76'*32
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE repeaters(public_key TEXT,name TEXT,adv_type INTEGER)')
        db.execute('INSERT INTO repeaters VALUES (?,?,2)',(key,'Hill'))
    before=path.read_bytes();monkeypatch.setattr(repeater_names,'DB_PATH',path)
    assert repeater_names.known_repeaters()==[{'public_key':key,'name':'Hill'}]
    assert path.read_bytes()==before


def test_missing_optional_directory_does_not_break_external_data(tmp_path,monkeypatch):
    path=tmp_path/'missing.db';monkeypatch.setattr(repeater_names,'DB_PATH',path)
    assert repeater_names.known_repeaters()==[] and not path.exists()
