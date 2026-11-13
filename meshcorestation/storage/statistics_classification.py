"""Bounded, disposable classifications of passive observations.

Only the collector writes source history. A source generation changes on edits,
deletes and non-append inserts. Each query reads it in its source WAL snapshot.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

CACHE_BYTES = 64 * 1024 * 1024
CACHE_FORMAT = 1
MAX_WINDOW_SECONDS = 60 * 86400
SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS classification_source(
 id INTEGER PRIMARY KEY CHECK(id=1), generation TEXT NOT NULL, highwater INTEGER NOT NULL);
INSERT OR IGNORE INTO classification_source
 SELECT 1,lower(hex(randomblob(16))),COALESCE(MAX(id),0) FROM observations;
CREATE TRIGGER IF NOT EXISTS classification_insert AFTER INSERT ON observations BEGIN
 UPDATE classification_source SET
   generation=CASE WHEN NEW.id<=highwater THEN lower(hex(randomblob(16))) ELSE generation END,
   highwater=MAX(highwater,NEW.id) WHERE id=1;
END;
CREATE TRIGGER IF NOT EXISTS classification_update AFTER UPDATE ON observations BEGIN
 UPDATE classification_source SET generation=lower(hex(randomblob(16))),
   highwater=MAX(highwater,NEW.id) WHERE id=1;
END;
CREATE TRIGGER IF NOT EXISTS classification_delete AFTER DELETE ON observations BEGIN
 UPDATE classification_source SET generation=lower(hex(randomblob(16))) WHERE id=1;
END;
"""
FACT_COLUMNS = """id INTEGER PRIMARY KEY,digest BLOB,at REAL,bucket INTEGER,
 kind INTEGER,hop INTEGER,confirmed INTEGER,region TEXT,origin INTEGER"""
EDGE_COLUMNS = "identity TEXT,direction TEXT,verified INTEGER,digest BLOB,at REAL,observation_id INTEGER"


@contextmanager
def transaction(db):
    db.execute('BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def source_marker(source, path, key, registry, regions):
    if not source.execute("SELECT 1 FROM sqlite_master WHERE name='classification_source'").fetchone():
        return None
    generation, highwater = source.execute('SELECT generation,highwater FROM classification_source WHERE id=1').fetchone()
    stat = path.stat()
    marker = hashlib.sha256(json.dumps([
        CACHE_FORMAT, key, stat.st_dev, stat.st_ino, generation, sorted(registry),
        sorted((r['name'], r['scope_key']) for r in regions),
    ]).encode()).hexdigest()
    return marker, highwater


def source_anchor(source, row_id):
    row = source.execute('SELECT reception_id FROM observations WHERE id=?', (row_id,)).fetchone()
    return row[0] if row else None


class ClassificationCache:
    """One retained interval for one repeater per installation."""

    def __init__(self, work, main_path):
        self.db = work
        self.path = Path(main_path).parent / 'statistics-classification.sqlite'
        self.previous = None

    def load(self, marker, highwater, start, end, source):
        if not self.path.exists():
            self.path.touch(mode=0o600, exist_ok=True)
        db = self.db
        db.execute('ATTACH DATABASE ? AS saved', (str(self.path),))
        pages = CACHE_BYTES // db.execute('PRAGMA saved.page_size').fetchone()[0]
        db.execute(f'PRAGMA saved.max_page_count={pages}')
        db.execute('PRAGMA saved.cache_size=-2048')
        db.execute('PRAGMA saved.journal_mode=TRUNCATE')
        db.execute('PRAGMA saved.synchronous=NORMAL')
        with transaction(db):
            db.execute('CREATE TABLE IF NOT EXISTS saved.cache_state(marker TEXT, highwater INTEGER, lo REAL, hi REAL, anchor TEXT)')
            db.execute(f'CREATE TABLE IF NOT EXISTS saved.facts({FACT_COLUMNS})')
            db.execute(f'CREATE TABLE IF NOT EXISTS saved.edges({EDGE_COLUMNS})')
            self.previous = db.execute('SELECT marker,highwater,lo,hi,anchor FROM saved.cache_state').fetchone()
            if self.previous is None:
                return None
            old_marker, old_id, lo, hi, anchor = self.previous
            if old_marker != marker or old_id > highwater or lo >= end or hi <= start:
                return None
            if anchor != source_anchor(source, old_id):
                return None
            lo, hi = max(start, lo), min(end, hi)
            db.execute('INSERT INTO facts SELECT * FROM saved.facts WHERE at>=? AND at<?', (lo, hi))
            db.execute('INSERT INTO edges SELECT * FROM saved.edges WHERE at>=? AND at<?', (lo, hi))
        return lo, hi, old_id

    def save(self, marker, highwater, start, end, reused, retain, anchor):
        db = self.db
        with transaction(db):
            # Do not overwrite a different reader's newer result.
            if self.previous != db.execute('SELECT marker,highwater,lo,hi,anchor FROM saved.cache_state').fetchone():
                return False
            if reused:
                lo, hi, old_id = reused
                old_start, old_end = self.previous[2:4]
                keep_start, keep_end = min(start, old_start), max(end, old_end)
                keep_start = min(start, max(keep_start, keep_end - MAX_WINDOW_SECONDS))
                keep_end = min(keep_end, keep_start + MAX_WINDOW_SECONDS)
                if not retain:
                    keep_start, keep_end = start, end
                for table in ('facts', 'edges'):
                    db.execute(f'DELETE FROM saved.{table} WHERE at<? OR at>=?', (keep_start, keep_end))
                for table, column in (('facts', 'id'), ('edges', 'observation_id')):
                    db.execute(f'''INSERT INTO saved.{table} SELECT * FROM main.{table}
                        WHERE {column}<=? AND (at<? OR at>=? OR {column}>?)''', (highwater, lo, hi, old_id))
            else:
                keep_start, keep_end = start, end
                for table, column in (('facts', 'id'), ('edges', 'observation_id')):
                    db.execute(f'DELETE FROM saved.{table}')
                    db.execute(f'INSERT INTO saved.{table} SELECT * FROM main.{table} WHERE {column}<=?', (highwater,))
            db.execute('DELETE FROM saved.cache_state')
            db.execute('INSERT INTO saved.cache_state VALUES(?,?,?,?,?)', (marker, highwater, keep_start, keep_end, anchor))
        return True
