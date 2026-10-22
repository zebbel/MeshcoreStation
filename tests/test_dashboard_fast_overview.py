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
