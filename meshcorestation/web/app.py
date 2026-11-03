"""Assemble the dashboard and its HTTP endpoints."""
from pathlib import Path
from dash import Dash
from meshcorestation.web.layout import build_layout
from meshcorestation.web.callbacks import register_callbacks
from meshcorestation.web.companion_settings import register_companion_routes
from meshcorestation.web.map_routes import register_map_routes


def create_app():
    # Bootstrap fresh V5 storage even when the dashboard is started without a radio.
    import logging
    from meshcorestation.storage.database import Database
    owner=Database(logging.getLogger('meshcorestation'));owner.close()
    app = Dash(__name__, title="MeshcoreStation", update_title=None, assets_folder=str(Path(__file__).with_name("assets")), assets_ignore=r"^(?:leaflet(?:\.markercluster)?\.(?:js|css)|MarkerCluster\.css)$", assets_path_ignore=[r"vendor/(?:leaflet(?:\.markercluster)?\.(?:js|css)|MarkerCluster\.css)$"])
    app.index_string = app.index_string.replace("{%favicon%}", '<link rel="icon" type="image/png" href="/assets/meshcore-logo.png?v=1.2">')
    from meshcorestation.updater import local_revision
    try:
        revision = local_revision()
    except Exception:
        revision = 'unknown'
    app.index_string = app.index_string.replace('{%metas%}', '{%metas%}<meta name="meshcorestation-revision" content="' + revision + '">')
    from flask import request,jsonify
    @app.server.before_request
    def reject_unimplemented_pages():
        if request.url_rule and request.url_rule.rule=='/<path:path>':
            return jsonify(ok=False,error='This page or API is not included in V5 milestone 1.'),404
    app.layout = build_layout
    register_callbacks(app)
    register_companion_routes(app.server)
    register_map_routes(app.server)
    from meshcorestation.web.display_api import register_display_routes
    register_display_routes(app.server)
    from meshcorestation.web.voltage_api import register_battery_template_routes
    register_battery_template_routes(app.server)
    from meshcorestation.web.update_api import register_update_routes
    register_update_routes(app.server)
    from meshcorestation.web.firmware_api import register_firmware_routes
    from meshcorestation.web.reply_api import register_reply_routes
    register_firmware_routes(app.server)
    register_reply_routes(app.server)
    from meshcorestation.web.statistics_api import register_statistics_routes
    register_statistics_routes(app.server)
    from meshcorestation.web.comparison_api import register_comparison_routes
    register_comparison_routes(app.server)
    return app
