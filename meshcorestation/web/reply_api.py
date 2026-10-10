"""Read-only outgoing reply evidence for command details."""
import sqlite3
from contextlib import closing
from urllib.parse import urlsplit
from flask import jsonify,request
from meshcorestation.config import DB_PATH
from meshcorestation.storage.reply_store import snapshot
from meshcorestation.web.companion_settings import allowed_host


def register_reply_routes(server):
    @server.get('/api/replies/<int:command_id>')
    def replies(command_id):
        origin=request.headers.get('Origin')
        if (not allowed_host((urlsplit(request.host_url).hostname or '').lower())
                or request.headers.get('X-Meshcore-Control')!='1'
                or request.headers.get('Sec-Fetch-Site')=='cross-site'
                or (origin and origin!=request.host_url.rstrip('/'))):
            return jsonify(error='Open command details from this dashboard.'),403
        try:
            with closing(sqlite3.connect(DB_PATH.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
                db.row_factory=sqlite3.Row
                if not db.execute('SELECT 1 FROM logger WHERE id=?',(command_id,)).fetchone():
                    return jsonify(error='Command not found.'),404
                response=jsonify(snapshot(db,command_id))
                response.headers['Cache-Control']='no-store'
                return response
        except sqlite3.Error:
            return jsonify(error='Reply tracking unavailable. Restart the updated station.'),503
