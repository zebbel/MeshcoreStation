"""Bounded persistent audit trail; never stores session tokens or passwords."""
import sqlite3
import time
from contextlib import contextmanager
from meshcorestation.config import DATA_DIR

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


def begin(key,field,before,value):
    with database() as db:
        ident=db.execute('INSERT INTO changes(at,public_key,field,before_value,requested,status) VALUES(?,?,?,?,?,?)',
                         (time.time(),key,field,str(before),str(value),'pending / outcome unknown')).lastrowid
        db.execute('DELETE FROM changes WHERE at<?',(time.time()-365*86400,))
        return ident


def finish(ident,actual,status):
    with database() as db:
        db.execute('UPDATE changes SET actual=?,status=? WHERE id=?',(None if actual is None else str(actual),status,ident))


def recent(key):
    with database() as db:
        return [dict(row) for row in db.execute('SELECT * FROM changes WHERE public_key=? ORDER BY id DESC LIMIT 50',(key,))]
