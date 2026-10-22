"""Bounded persistent audit trail; never stores session tokens or passwords."""
import sqlite3
import time
from contextlib import contextmanager
from meshcorestation.config import DATA_DIR
from meshcorestation.storage import optimizer_store

FILE = DATA_DIR / 'repeater-advisor-history.db'

@contextmanager
def database():
    FILE.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(FILE,timeout=5)
    db.row_factory=sqlite3.Row
    try:
        db.execute('CREATE TABLE IF NOT EXISTS changes (id INTEGER PRIMARY KEY, at REAL, public_key TEXT, field TEXT, before_value TEXT, requested TEXT, actual TEXT, status TEXT)')
        with db: yield db
    finally: db.close()


@optimizer_store.synchronized
def begin(key,field,before,value):
    if not optimizer_store.status()['enabled']:
        return None
    with database() as db:
        # Do not reuse an erased row ID: an in-flight readback may still finish.
        ident=db.execute('INSERT INTO changes(id,at,public_key,field,before_value,requested,status) VALUES(?,?,?,?,?,?,?)',
                         (max(time.time_ns()//1000, db.execute('SELECT COALESCE(MAX(id),0)+1 FROM changes').fetchone()[0]),time.time(),key,field,str(before),str(value),'pending / outcome unknown')).lastrowid
        db.execute('DELETE FROM changes WHERE at<?',(time.time()-365*86400,))
        return ident


@optimizer_store.synchronized
def finish(ident,actual,status):
    with database() as db:
        db.execute('UPDATE changes SET actual=?,status=? WHERE id=?',(None if actual is None else str(actual),status,ident))


def recent(key):
    with database() as db:
        return [dict(row) for row in db.execute('SELECT * FROM changes WHERE public_key=? ORDER BY id DESC LIMIT 50',(key,))]



@optimizer_store.synchronized
def clear_verified_flood(key):
    """Clear verified optimizer changes for ONE repeater only.

    Before/after entries are derived from these records and disappear with
    them. Do not erase pending, failed, or unrelated configuration audits.
    This is a local database operation with no radio traffic.
    """
    from meshcorestation.storage.optimizer_store import valid_key
    valid_key(key)
    with database() as db:
        cursor=db.execute("""DELETE FROM changes
            WHERE public_key=? AND status='verified'
              AND field IN ('flood.max', 'flood.max.unscoped')""",(key,))
        return cursor.rowcount


def remove_repeater(key):
    """Forget one removed repeater's optimizer audit and derived comparisons."""
    from meshcorestation.storage.optimizer_store import valid_key
    valid_key(key)
    if not FILE.exists():
        return
    with database() as db:
        db.execute('DELETE FROM changes WHERE public_key=?', (key,))
