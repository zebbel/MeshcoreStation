"""Periodic dashboard refresh, pagination, and command table rendering."""
import json
import logging
import sqlite3
from datetime import datetime
from dash import Input, Output, State, ctx, html, no_update
from meshcorestation.web.data import PAGE_SIZE, TIMEZONE, bot_status, snapshot, timestamp


def register_callbacks(app):
    def table_rows(rows):
        if not rows:
            return [html.Tr(html.Td("No recorded commands match this filter.", colSpan=4, className="empty"))]
        result = []
        for row in rows:
            details = dict(row)
            for key in ("recv_time", "sender_timestamp", "sender_position_updated_at"):
                if details.get(key) is not None:
                    details[key] = f"{timestamp(details[key])} · Unix {details[key]}"
            result.append(html.Tr([html.Td(timestamp(row.get("recv_time")), className="date"), html.Td(row.get("message") or "—", className="command"), html.Td(row.get("sender") or "—"), html.Td(html.Button("Info ↗", className="info-button", **{"data-details": json.dumps(details, default=str), "aria-label": f"Details for command {row['id']}"}))], **{"data-row-id": str(row["id"])}))
        return result


    @app.callback(Output("window-size", "data"), Input("command-filter", "value"), Input("load-older", "n_clicks"), State("window-size", "data"), prevent_initial_call=True)
    def change_window(command, clicks, size):
        return (size or PAGE_SIZE) + PAGE_SIZE if ctx.triggered_id == "load-older" else PAGE_SIZE


    @app.callback(Output("bot-status", "children"), Output("bot-status", "className"), Output("bot-detail", "children"), Output("repeater-count", "children"), Output("repeater-detail", "children"), Output("last-command", "children"), Output("last-detail", "children"), Output("command-filter", "options"), Output("command-rows", "children"), Output("command-rows", "data-filter"), Output("row-count", "children"), Output("load-older", "disabled"), Output("error", "children"), Output("updated", "children"), Output("last-render", "data"), Output("history-zone", "children"), Input("refresh", "n_intervals"), Input("command-filter", "value"), Input("window-size", "data"), State("last-render", "data"))
    def refresh_dashboard(tick, command, size, previous):
        status, detail, status_class = bot_status()
        zone_label = f"Oldest to newest · {TIMEZONE.key}"
        try:
            data = snapshot(command, size or PAGE_SIZE)
        except (sqlite3.Error, OSError) as exc:
            logging.warning("Dashboard database read failed: %s", exc)
            return status, "metric " + status_class, detail, "—", "Database unavailable", "—", "Database unavailable", no_update, no_update, no_update, "Data unavailable", True, "Cannot read the bot database. Check MESHCORESTATION_DATA_DIR and file permissions. Previously displayed rows may be stale; retrying automatically.", "Refresh failed", no_update, zone_label
        latest = data["latest"]
        latest_text = latest.get("message") or "—" if latest else "No commands yet"
        latest_detail = f"{latest.get('sender') or 'Unknown sender'} · {timestamp(latest.get('recv_time'))}" if latest else "Waiting for the first saved command"
        signature = json.dumps([command, data["rows"]], sort_keys=True, default=str)
        rows = table_rows(data["rows"]) if signature != previous else no_update
        options = [{"label": value if value else "(empty command)", "value": value} for value in data["commands"]]
        if command is not None and command not in data["commands"]:
            options.append({"label": command + " (no records)", "value": command})
        return status, "metric " + status_class, detail, f"{data['repeaters']:,}", "Recorded by your bot", latest_text, latest_detail, options, rows, json.dumps(command), f"{len(data['rows']):,} of {data['total']:,} commands", len(data["rows"]) >= data["total"], "", "Updated " + datetime.now(TIMEZONE).strftime("%H:%M:%S %Z"), signature, zone_label
