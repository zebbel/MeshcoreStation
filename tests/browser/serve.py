"""Disposable local HTTP app for browser regressions; never starts a radio."""
import logging
import tempfile
import os
from pathlib import Path

# Before any application imports, keep every database outside the checkout.
with tempfile.TemporaryDirectory(prefix='meshcorestation-browser-') as directory:
    os.environ['MESHCORESTATION_DATA_DIR']=directory
    from meshcorestation.storage.database import Database
    from meshcorestation.storage import voltage_store, passive_stats
    from meshcorestation.web.app import create_app
    key='769b90b4dd327d7bc9cc651fb8d2f8a4a217957cd36feac6b3216b5acedc36ff'
    other='ab'*32
    owner=Database(logging.getLogger('browser-test'));voltage_store.initialize(owner.db)
    with owner.db:
        for public_key,name in ((key,'DE_HE_HP_RPT1'),(other,'Second Repeater')):
            owner.db.execute('INSERT INTO repeaters(public_key,name,adv_type,first_seen,last_seen) VALUES (?,?,2,0,0)',(public_key,name))
            voltage_store.ensure_repeater(owner.db,public_key)
    owner.close();passive_stats.initialize();passive_stats.track(key);passive_stats.track(other)
    create_app().server.run(host='127.0.0.1',port=8050,debug=False,use_reloader=False)
