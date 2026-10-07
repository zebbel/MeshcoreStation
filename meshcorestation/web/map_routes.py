"""Read-only HTTP endpoints for repeater and packet route maps."""
import sqlite3
from flask import jsonify
from meshcorestation.web.maps import repeater_map, route_map

def register_map_routes(server):
    @server.get("/api/maps/repeaters")
    def api_repeaters():
        return map_response(repeater_map)


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
