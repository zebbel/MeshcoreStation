"""Map endpoints and local repeater registry controls."""
import sqlite3
from flask import jsonify, request
from meshcorestation.storage import registry
from meshcorestation.web import data
from meshcorestation.web.http import control_request_error, json_response
from meshcorestation.web.maps import repeater_map, route_map

def register_map_routes(server):
    @server.get("/api/maps/repeaters")
    def api_repeaters():
        return map_response(repeater_map)


    @server.route('/api/repeater-registry', methods=['GET', 'POST'])
    def api_registry():
        if control_request_error():
            return json_response(dict(ok=False, error='Open repeater registry controls from the local dashboard.'), 403)
        try:
            if request.method == 'GET':
                return json_response(dict(ok=True, blocked=registry.blocked_repeaters(data.DB_PATH.with_name('knownRepeaters.db'))))
            if request.mimetype != 'application/json' or not 0 < (request.content_length or 0) <= 1024:
                raise ValueError('Invalid repeater registry request.')
            body = request.get_json(silent=True)
            if not isinstance(body, dict) or set(body) != {'action', 'public_key', 'confirm'}:
                raise ValueError('Invalid repeater registry request.')
            if body['confirm'] is not True:
                raise ValueError('Confirm the repeater registry action.')
            if not isinstance(body['public_key'], str):
                raise ValueError('A full 64-hex public key is required.')
            registry.change_visibility(data.DB_PATH, body['public_key'], body['action'])
            return json_response(dict(ok=True))
        except registry.ManagedRepeaterError as exc:
            return json_response(dict(ok=False, error=str(exc)), 409)
        except ValueError as exc:
            return json_response(dict(ok=False, error=str(exc)), 400)
        except (sqlite3.Error, OSError):
            return json_response(dict(ok=False, error='Repeater registry unavailable. Refresh and try again.'), 503)

    @server.get("/api/maps/route/<int:log_id>")
    def api_route(log_id):
        return map_response(lambda: route_map(log_id))


    def map_response(loader):
        try:
            payload = loader()
            response = jsonify(payload if payload is not None else {"error": "This command is no longer in the database."})
            response.status_code = 200 if payload is not None else 404
        except (sqlite3.Error, OSError):
            response = jsonify({"error": "Map data unavailable. Check the bot database and try opening the map again."})
            response.status_code = 503
        response.headers["Cache-Control"] = "no-store"
        return response
