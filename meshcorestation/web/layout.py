"""Dashboard layout and top-level settings actions."""
from dash import dcc, html
import sqlite3
from meshcorestation.web.data import PAGE_SIZE, bot_status, overview, timestamp

def popup(children, **attributes):
    # Only the body scrolls; the header remains outside the scrolling region.
    return html.Dialog([children[0], html.Div(children[1:], className="dialog-body")], **attributes)


def card(label, value_id, detail_id, value="—", detail="Waiting for data", metric_class="metric"):
    heading = html.P(label, className="eyebrow")
    if value_id in {"bot-status", "repeater-count"}:
        button = html.Button("Settings", id="open-companion", className="info-button") if value_id == "bot-status" else html.Button("Map ↗", id="open-repeaters", className="info-button")
        heading = html.Div([heading, button], className="card-heading")
    return html.Section([heading, html.Div(value, id=value_id, className=metric_class), html.P(detail, id=detail_id, className="muted")], className="card")

def build_layout():
    status, status_detail, status_class = bot_status()
    try:
        summary = overview()
        count, repeater_detail = f"{summary['repeaters']:,}", "Recorded by your bot"
    except (sqlite3.Error, OSError):
        summary = {"latest": None}
        count, repeater_detail = "—", "Database unavailable"
    latest = summary["latest"]
    latest_command = (latest.get("message") or "—") if latest else "No commands yet"
    latest_detail = (f"{latest.get('sender') or 'Unknown sender'} · {timestamp(latest.get('recv_time'))}"
                     if latest else "Waiting for the first saved command")
    return html.Main([
        html.Header([html.Div([html.Div([html.Img(src="/assets/meshcore-logo.png?v=1.2", id="meshcore-brand-image", alt="MeshCore"), html.Span("M", id="brand-fallback", hidden=True)], className="mark meshcore-mark"), html.Div([html.H1("MeshcoreStation"), html.P("Your mesh, at a glance.", className="muted")])], className="brand"), html.Div([html.Span(className="live-dot"), " Refreshes every 5 seconds"], className="refresh-label")]),
        html.Div([card("Bot status", "bot-status", "bot-detail", status, status_detail, "metric " + status_class), card("Known repeaters", "repeater-count", "repeater-detail", count, repeater_detail)], className="cards"),
    html.Div(id="error", role="status"),
        html.Section([html.Details([
            html.Summary([
                html.H2("Command history"),
                html.Div([html.P("Last command received", className="eyebrow"), html.Div(latest_command, id="last-command", className="history-latest-command"), html.P(latest_detail, id="last-detail", className="muted")], className="history-latest"),
                html.Button("Commands", id="open-commands", className="info-button", type="button")
            ], className="command-history-summary"),
            html.Div([html.Div([html.P("Oldest to newest · Europe/Berlin", className="muted", id="history-zone")]), html.Div([html.Label("Command", htmlFor="command-filter"), dcc.Dropdown(id="command-filter", options=[], placeholder="All commands", clearable=True, className="command-filter")], className="filter")], className="toolbar"),
            html.Div([html.Button("Load older", id="load-older", n_clicks=0, className="secondary"), html.Span(id="row-count", className="muted"), html.Button("↓ Latest", id="jump-latest", className="secondary")], className="list-tools"),
            html.Div(html.Table([html.Thead(html.Tr([html.Th("Date & time"), html.Th("Command"), html.Th("Received from"), html.Th("Details")])), html.Tbody(id="command-rows")]), id="command-scroll", tabIndex=0, **{"aria-label": "Command history, oldest first"}),
            html.Div(id="updated", className="updated muted")
        ], id="command-history-disclosure", className="panel-disclosure")], className="history"),
        html.Section(html.Details([
            html.Summary(html.H2("Repeater management")),
            html.Div([
                html.Label([html.Span("Selected repeater"), html.Select(id="managed-repeater", **{"aria-label": "Selected repeater"})]),
                html.Div([
                    html.Button("Add repeater from map", id="managed-repeater-add", type="button", className="info-button"),
                    html.Button("Open repeater management", id="managed-repeater-open", type="button", className="info-button", disabled=True),
                    html.Button("Remove repeater", id="managed-repeater-remove", type="button", className="info-button", disabled=True)
                ], className="managed-repeater-actions")
            ], className="managed-repeater-controls"),
            html.P(id="managed-repeater-message", role="status"),
            html.Section([
                html.Div([html.H2("Repeater telemetry"), html.Button("Telemetry history / settings", id="open-voltage", className="info-button")], className="toolbar"),
                html.Div(id="battery-overview")
            ], className="managed-repeater-section")
        ], id="repeater-management-disclosure", className="panel-disclosure"), className="history"),
        html.Section(html.Details([
            html.Summary(html.H2("Repeater Optimizer")),
            html.P("All subsections use the repeater selected in Repeater Management.", className="muted"),
            html.Details([
                html.Summary(html.H2("Repeater statistics")),
                html.Div(html.Div(id="repeater-statistics-inline"), className="optimizer-section-body")
            ], id="repeater-statistics-disclosure", className="panel-disclosure managed-repeater-section"),
            html.Details([
                html.Summary(html.H2("Optimization Analysis")),
                html.Div([html.P("Passive analysis loads on opening. Protected actions require an administrator session and explicit confirmation.", className="muted"),
                html.Div([html.Button("Connect as administrator", id="analysis-connect"),
                          html.Button("Disconnect administrator", id="analysis-disconnect")], className="stats-controls"),
                html.Div(id="optimization-analysis-inline")], className="optimizer-section-body")
            ], id="optimization-analysis-disclosure", className="panel-disclosure managed-repeater-section"),
            html.Details([
                html.Summary(html.H2("Repeater Network Monitoring")),
                html.Div([html.P("External Analyzer observations depend on participating observers. Missing evidence does not prove poor radio connectivity. Inferred relationships are not verified direct radio links. Loads on opening with a five-minute cache. External access may be restricted.", className="muted"),
                html.Div([html.Span(id="network-selected", className="stats-selected"),
                          html.Button("Refresh Now", id="network-refresh")], className="stats-controls"),
                html.P(id="network-status", className="stats-message", role="status", **{"aria-live": "polite"}),
                html.Div(id="network-content")], className="optimizer-section-body")
            ], id="repeater-network-disclosure", className="panel-disclosure managed-repeater-section")
        ], id="repeater-optimizer-disclosure", className="panel-disclosure"), className="history"),
        html.Section(html.Details([
            html.Summary(html.H2("Room server")),
            html.Div(html.Iframe(src="about:blank", id="room-server-frame", **{"data-src": "/rooms?embedded=1"},
                                title="Room server controls", style={"width": "100%", "height": "160px", "border": "0", "display": "block"}),
                     className="room-server-inline")
        ], id="room-server-disclosure", className="panel-disclosure"), className="history"),
        popup([html.Div([html.Div([html.P("COMMAND DETAILS", className="eyebrow"), html.H2("Received command", id="detail-title")]), html.Button("×", id="close-details", **{"aria-label": "Close details"})], className="dialog-header"), html.P("Reply text is recorded by the bot; it is not proof of delivery.", className="muted"), html.Section([html.H3("Packet route"), html.Div(id="route-summary", className="route-summary", **{"aria-live": "polite"}), html.Div(id="route-paths", className="route-paths", role="group", **{"aria-label": "Reception paths"}), html.Div(id="route-map", className="map-canvas", role="region", **{"aria-label": "Packet route map"}), html.Div(id="route-notes", className="map-notes")], id="route-section", hidden=True), html.Dl(id="detail-fields")], id="details-dialog", **{"aria-labelledby": "detail-title"}),
        popup([html.Div([html.H2("Known repeaters", id="repeaters-title"), html.Button("×", id="close-repeaters", **{"aria-label": "Close repeater map"})], className="dialog-header"), html.Div(id="repeater-notes", className="map-notes", **{"aria-live": "polite"}), html.Div(id="repeater-map", className="map-canvas", role="region", **{"aria-label": "Known repeaters map"})], id="repeaters-dialog", **{"aria-labelledby": "repeaters-title"}),
        dcc.Interval(id="refresh", interval=5000), dcc.Interval(id="history-refresh", interval=5000, disabled=True), dcc.Store(id="window-size", data=PAGE_SIZE), dcc.Store(id="last-render", data=None), dcc.Store(id="history-visible", data=False)
    ], className="shell")
