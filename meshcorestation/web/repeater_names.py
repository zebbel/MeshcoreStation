"""Small local name directory piggybacked on existing on-demand responses."""
from contextlib import closing
import sqlite3
from meshcorestation.config import DB_PATH


def known_repeaters():
    try:
        with closing(sqlite3.connect(DB_PATH.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
            return [{'public_key':key,'name':name} for key,name in db.execute(
                'SELECT public_key,name FROM repeaters WHERE adv_type=2')]
    except (sqlite3.Error,OSError):
        # External evidence can still be used if the optional local directory fails.
        return []
