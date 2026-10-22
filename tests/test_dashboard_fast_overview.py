"""Fast initial summary is independent of the command history query."""
import sqlite3
from meshcorestation.web import data, layout


def test_overview_returns_saved_counts_and_latest_without_full_history(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE repeaters(public_key TEXT PRIMARY KEY);
            CREATE TABLE logger(id INTEGER PRIMARY KEY, message TEXT, sender TEXT, recv_time INTEGER);
            INSERT INTO repeaters VALUES ('ab'), ('cd');
            INSERT INTO logger VALUES (1, 'status', 'Alice', 10);
            INSERT INTO logger VALUES (2, 'ping', 'Bob', 11);
        """)
    monkeypatch.setattr(data, "DB_PATH", db_path)
    overview = data.overview()
    assert overview == {"repeaters": 2, "latest": {"id": 2, "message": "ping", "sender": "Bob", "recv_time": 11}}
    monkeypatch.setattr(layout, "bot_status", lambda: ("Running", "Connected", "running"))
    page = layout.build_layout()
    cards = next(node for node in page.children if getattr(node, "className", None) == "cards")
    assert cards.children[0].children[1].children == "Running"
    assert cards.children[1].children[1].children == "2"


def test_map_libraries_are_lazy_but_still_served():
    from meshcorestation.web.app import create_app

    app = create_app()
    client = app.server.test_client()
    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "aa_map_loader.js" in page
    assert "/assets/vendor/leaflet.js" not in page
    assert "/assets/vendor/leaflet.markercluster.js" not in page
    assert client.get("/assets/vendor/leaflet.js").status_code == 200
    assert client.get("/assets/vendor/leaflet.markercluster.js").status_code == 200
    assert "/assets/vendor/leaflet.css" not in page
    for path in ("/rooms", "/repeater-optimizer", "/repeater-advisor"):
        tool=client.get(path)
        assert tool.status_code==200
        assert 'meshcorestation-display' in tool.text
        assert '/assets/aa_display.js' in tool.text


def test_closed_history_never_queries_database(monkeypatch):
    from meshcorestation.web.app import create_app
    from meshcorestation.web import callbacks
    def forbidden(*args):
        raise AssertionError('Closed history queried the database')
    monkeypatch.setattr(callbacks,'snapshot',forbidden)
    app=create_app()
    callback=next(value['callback'] for name,value in app.callback_map.items() if 'command-rows' in name)
    from dash import no_update
    assert callback.__wrapped__(0,None,200,False,None)==(no_update,)*8
