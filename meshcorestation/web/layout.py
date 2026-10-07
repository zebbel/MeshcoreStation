"""Dashboard layout and top-level settings actions."""
from dash import dcc, html
from meshcorestation.web.data import PAGE_SIZE

def popup(children, **attributes):
    # Only the body scrolls; the header remains outside the scrolling region.
    return html.Dialog([children[0], html.Div(children[1:], className="dialog-body")], **attributes)


def card(label, value_id, detail_id):
    heading = html.P(label, className="eyebrow")
    if value_id in {"bot-status", "repeater-count"}:
        button = html.Button("Settings", id="open-companion", className="info-button") if value_id == "bot-status" else html.Button("Map ↗", id="open-repeaters", className="info-button")
        heading = html.Div([heading, button] + ([html.Button("Scopes", id="open-scopes", className="info-button"), html.Button("Commands", id="open-commands", className="info-button")] if value_id == "bot-status" else []), className="card-heading")
    return html.Section([heading, html.Div("—", id=value_id, className="metric"), html.P("Waiting for data", id=detail_id, className="muted")], className="card")

def build_layout():
    return html.Main([
        html.Header([html.Div([html.Div([html.Img(src="/assets/meshcore-logo.png?v=1.2", id="meshcore-brand-image", alt="MeshCore"), html.Span("M", id="brand-fallback", hidden=True)], className="mark meshcore-mark"), html.Div([html.H1("MeshcoreStation"), html.P("Your mesh, at a glance.", className="muted")])], className="brand"), html.Div([html.Span(className="live-dot"), " Refreshes every 5 seconds"], className="refresh-label")]),
        html.Div([card("Bot status", "bot-status", "bot-detail"), card("Known repeaters", "repeater-count", "repeater-detail"), card("Last command received", "last-command", "last-detail")], className="cards"),
    html.Div(id="error", role="status"),
        html.Section([html.Div([html.Div([html.H2("Repeater battery"), html.P("Voltage history and scheduled channel reports", className="muted")]), html.Button("Battery history / settings", id="open-voltage", className="info-button")], className="toolbar"), html.Div(id="battery-overview")], className="history"),
        html.Section([
            html.Div([html.Div([html.H2("Command history"), html.P("Oldest to newest · Europe/Berlin", className="muted", id="history-zone")]), html.Div([html.Label("Command", htmlFor="command-filter"), dcc.Dropdown(id="command-filter", options=[], placeholder="All commands", clearable=True, className="command-filter")], className="filter")], className="toolbar"),
            html.Div([html.Button("Load older", id="load-older", n_clicks=0, className="secondary"), html.Span(id="row-count", className="muted"), html.Button("↓ Latest", id="jump-latest", className="secondary")], className="list-tools"),
            html.Div(html.Table([html.Thead(html.Tr([html.Th("Date & time"), html.Th("Command"), html.Th("Received from"), html.Th("Details")])), html.Tbody(id="command-rows")]), id="command-scroll", tabIndex=0, **{"aria-label": "Command history, oldest first"}),
            html.Div(id="updated", className="updated muted")
        ], className="history"),
        popup([html.Div([html.Div([html.P("COMMAND DETAILS", className="eyebrow"), html.H2("Received command", id="detail-title")]), html.Button("×", id="close-details", **{"aria-label": "Close details"})], className="dialog-header"), html.P("Reply text is recorded by the bot; it is not proof of delivery.", className="muted"), html.Section([html.H3("Packet route"), html.Div(id="route-map", className="map-canvas", role="region", **{"aria-label": "Packet route map"}), html.Div(id="route-notes", className="map-notes"), html.Ol(id="route-hops", className="hop-list")], id="route-section", hidden=True), html.Dl(id="detail-fields")], id="details-dialog", **{"aria-labelledby": "detail-title"}),
        popup([html.Div([html.H2("Known repeaters", id="repeaters-title"), html.Button("×", id="close-repeaters", **{"aria-label": "Close repeater map"})], className="dialog-header"), html.Div(id="repeater-map", className="map-canvas", role="region", **{"aria-label": "Known repeaters map"}), html.Div(id="repeater-notes", className="map-notes")], id="repeaters-dialog", **{"aria-labelledby": "repeaters-title"}),
        dcc.Interval(id="refresh", interval=5000), dcc.Store(id="window-size", data=PAGE_SIZE), dcc.Store(id="last-render", data=None)
    ], className="shell")
