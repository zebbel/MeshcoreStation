"""Assemble the dashboard and its HTTP endpoints."""
from pathlib import Path
from dash import Dash
from meshcorestation.web.layout import build_layout
from meshcorestation.web.callbacks import register_callbacks
from meshcorestation.web.companion_settings import register_companion_routes
from meshcorestation.web.map_routes import register_map_routes


def create_app():
    app = Dash(__name__, title="MeshcoreStation", update_title=None, assets_folder=str(Path(__file__).with_name("assets")), assets_ignore=r"^(?:leaflet(?:\.markercluster)?\.(?:js|css)|MarkerCluster\.css)$", assets_path_ignore=[r"vendor/(?:leaflet(?:\.markercluster)?\.(?:js|css)|MarkerCluster\.css)$"])
    app.index_string = app.index_string.replace("{%favicon%}", '<link rel="icon" type="image/png" href="/assets/meshcore-logo.png?v=1.2">')
    from meshcorestation.updater import local_revision
    try:
        revision = local_revision()
    except Exception:
        revision = 'unknown'
    app.index_string = app.index_string.replace('{%metas%}', '{%metas%}<meta name="meshcorestation-revision" content="' + revision + '">')
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
    register_firmware_routes(app.server)
    from meshcorestation.web.passive_api import register_passive_routes
    register_passive_routes(app.server)
    from meshcorestation.web.oled_api import register_oled_routes
    register_oled_routes(app.server)
    from meshcorestation.web.reply_api import register_reply_routes
    register_reply_routes(app.server)
    from meshcorestation.web.rooms_api import register_room_routes
    register_room_routes(app.server)
    from meshcorestation.web.optimizer_api import register_optimizer_routes
    register_optimizer_routes(app.server)
    return app
