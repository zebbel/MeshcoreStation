"""Local-origin OLED editing; SQL sources are selected from fixed catalogs."""
import json
import sqlite3
import time
from contextlib import closing
from urllib.parse import urlsplit
from flask import jsonify, request
from meshcorestation.config import DB_PATH
from meshcorestation.storage import oled_store as store
from meshcorestation.radio.oled_scene import render
from meshcorestation.web.companion_settings import allowed_host


def register_oled_routes(server):
    @server.route('/api/oled/pages',methods=['GET','POST'])
    def oled_pages():
        def reply(body, status=200):
            response = jsonify(body)
            response.status_code = status
            response.headers['Cache-Control'] = 'no-store'
            return response
        origin = request.headers.get('Origin')
        if (not allowed_host((urlsplit(request.host_url).hostname or '').lower())
                or request.headers.get('X-Meshcore-Control') != '1'
                or request.headers.get('Sec-Fetch-Site') == 'cross-site'
                or (origin and origin != request.host_url.rstrip('/'))):
            return reply(dict(ok=False,error='Open the OLED editor from this dashboard.'),403)
        try:
            with closing(sqlite3.connect(DB_PATH.as_uri()+'?mode=rw',uri=True,timeout=3)) as db:
                db.row_factory = sqlite3.Row
                if request.method=='GET':
                    return reply({**store.snapshot(db),'values':store.VALUES,'series':store.SERIES})
                if request.mimetype != 'application/json':
                    return reply(dict(ok=False,error='Expected JSON.'),415)
                raw = request.stream.read(65537)
                if len(raw)>65536:
                    raise ValueError('Document too large.')
                body = json.loads(raw)
                if not isinstance(body,dict):
                    raise ValueError('Invalid request.')
                action = body.get('action')
                if action=='save':
                    with db:
                        return reply(store.save(db,body.get('pages'),body.get('revision')))
                if action=='stop_preview':
                    with db:
                        db.execute('UPDATE oled_pages SET preview=NULL,preview_until=0 WHERE id=1')
                    return reply(dict(ok=True))
                if action not in ('preview','device_preview'):
                    raise ValueError('Unknown action.')
                pages = store.validate(body.get('pages'))
                index = body.get('page',0)
                if type(index) is not int or not 0<=index<len(pages):
                    raise ValueError('Select a page.')
                drawing = render(db,pages[index],time.time())
                if action=='device_preview':
                    from meshcorestation.bridge import bridge
                    display = getattr(bridge.runtime,'oled',None)
                    # Runtime owns the connection; never start a second USB reader.
                    if display is None or display.task is None or display.task.done() or not display.acquired:
                        raise ValueError('Companion OLED is not active. Connect compatible firmware first.')
                    with db:
                        db.execute('UPDATE oled_pages SET preview=?,preview_until=? WHERE id=1',
                                   (json.dumps(pages[index]),time.time()+30))
                return reply(dict(ok=True,drawing=drawing))
        except RuntimeError as exc:
            return reply(dict(ok=False,error=str(exc)),409)
        except (ValueError,TypeError,KeyError) as exc:
            return reply(dict(ok=False,error=str(exc)),400)
        except sqlite3.Error:
            return reply(dict(ok=False,error='OLED database unavailable. Restart the updated station.'),503)
