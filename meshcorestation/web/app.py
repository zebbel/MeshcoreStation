"""Assemble the dashboard and its HTTP endpoints."""
from pathlib import Path
from dash import Dash
from meshcorestation.web.layout import build_layout
from meshcorestation.web.callbacks import register_callbacks
from meshcorestation.web.companion_settings import register_companion_routes
from meshcorestation.web.map_routes import register_map_routes


def create_app():
    app = Dash(__name__, title="MeshcoreStation", update_title=None, assets_folder=str(Path(__file__).with_name("assets")))
    app.index_string = app.index_string.replace("{%favicon%}", '<link rel="icon" type="image/png" href="/assets/meshcore-logo.png?v=1.2">')
    from meshcorestation.updater import local_revision
    try:
        revision = local_revision()
    except Exception:
        revision = 'unknown'
    app.index_string = app.index_string.replace('{%metas%}', '{%metas%}<meta name="meshcorestation-revision" content="' + revision + '">')
    app.layout = build_layout()
    register_callbacks(app)
    register_companion_routes(app.server)
    register_map_routes(app.server)
    from meshcorestation.web.update_api import register_update_routes
    register_update_routes(app.server)
    from meshcorestation.web.passive_api import register_passive_routes
    register_passive_routes(app.server)
    return app
