"""Main database connections expose a read-only temporary registry view.

The view stores no identities in meshcorestation.db. It lets shared V4 protocol
readers query canonical repeater metadata without introducing a second registry.
"""
from pathlib import Path
import sqlite3
from meshcorestation.storage import registry


def connect(database,**kwargs):
    kwargs['uri']=True
    db=sqlite3.connect(database,**kwargs)
    db.row_factory=sqlite3.Row
    main=db.execute('PRAGMA database_list').fetchone()[2]
    known=Path(main).with_name('knownRepeaters.db')
    if not known.exists():registry.initialize(known)
    db.execute('ATTACH DATABASE ? AS known',(known.as_uri()+'?mode=ro',))
    db.execute('CREATE TEMP VIEW repeaters AS SELECT * FROM known.repeaters')
    db.execute('PRAGMA foreign_keys=ON')
    return db
