"""Read already-known connected firmware metadata; never flash or poll radio."""
from flask import jsonify
from meshcorestation.web.http import control_request_error
from meshcorestation.bridge import bridge


def register_firmware_routes(server):
    @server.get('/api/companion/firmware')
    def status():
        if control_request_error():return jsonify(ok=False,error='Open from this dashboard.'),403
        runtime=bridge.runtime
        companion=runtime.companion if runtime else None
        connected=bool(companion and companion.mc and companion.mc.connection_manager.is_connected)
        response=jsonify(ok=True,connected=connected,device=dict(runtime.device_info) if connected else {})
        response.headers['Cache-Control']='no-store'
        return response
