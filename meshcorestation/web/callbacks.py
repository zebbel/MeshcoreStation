"""Periodic dashboard refresh, pagination, and command table rendering."""
import json
import logging
import sqlite3
from meshcorestation.web.i18n import t
from datetime import datetime
from dash import Input, Output, State, ctx, html, no_update
from meshcorestation.web.data import PAGE_SIZE, TIMEZONE, bot_status, overview, history_snapshot, timestamp


def register_callbacks(app):
    def table_rows(rows, preferences):
        if not rows:
            return [html.Tr(html.Td(t('No recorded commands match this filter.'), colSpan=4, className="empty"))]
        result = []
        for row in rows:
            details = dict(row)
            received = timestamp(row.get("recv_time"), preferences)
            for key in ("recv_time", "sender_timestamp", "sender_position_updated_at"):
                if details.get(key) is not None:
                    formatted = received if key == "recv_time" else timestamp(details[key], preferences)
                    details[key] = f"{formatted} · Unix {details[key]}"
            result.append(html.Tr([html.Td(received, className="date"), html.Td(row.get("message") or "—", className="command"), html.Td(row.get("sender") or "—"), html.Td(html.Button(t('Info ↗'), className="info-button", **{"data-details": json.dumps(details, default=str), "aria-label": t('Details for command {0}', row['id'])}))], **{"data-row-id": str(row["id"])}))
        return result


    @app.callback(Output("window-size", "data"), Input("command-filter", "value"), Input("load-older", "n_clicks"), State("window-size", "data"), prevent_initial_call=True)
    def change_window(command, clicks, size):
        return (size or PAGE_SIZE) + PAGE_SIZE if ctx.triggered_id == "load-older" else PAGE_SIZE


    @app.callback(
        Output("bot-status", "children"), Output("bot-status", "className"),
        Output("bot-detail", "children"), Output("repeater-count", "children"),
        Output("repeater-detail", "children"), Output("last-command", "children"),
        Output("last-detail", "children"), Output("error", "children"),
        Input("refresh", "n_intervals"))
    def refresh_overview(tick):
        # Keep the visible cards independent of slower history/filter reads.
        status, detail, status_class = bot_status()
        status = t('Connected') if status == "Running" else t(status)
        detail = t(detail)
        try:
            summary = overview()
        except (sqlite3.Error, OSError) as exc:
            logging.warning("Dashboard summary read failed: %s", exc)
            return (status, "metric " + status_class, detail, "—", t('Database unavailable'),
                    "—", t('Database unavailable'),
                    t('Cannot read the bot database. Check MESHCORESTATION_DATA_DIR and file permissions; retrying automatically.'))
        latest = summary["latest"]
        latest_text = (latest.get("message") or "—") if latest else t('No commands yet')
        latest_detail = (f"{latest.get('sender') or t('Unknown sender')} · {timestamp(latest.get('recv_time'))}"
                         if latest else t('Waiting for the first saved command'))
        return (status, "metric " + status_class, detail, f"{summary['repeaters']:,}",
                t('Saved locally; available while disconnected.'), latest_text, latest_detail, "")

    @app.callback(
        Output("command-filter", "options"), Output("command-rows", "children"),
        Output("command-rows", "data-filter"), Output("row-count", "children"),
        Output("load-older", "disabled"), Output("updated", "children"),
        Output("last-render", "data"), Output("history-zone", "children"),
        Input("history-refresh", "n_intervals"), Input("command-filter", "value"),
        Input("window-size", "data"), Input("history-visible", "data"), State("last-render", "data"))
    def refresh_history(tick, command, size, visible, previous):
        if not visible:
            return (no_update,) * 8
        zone_label = t('Oldest to newest · {0}', TIMEZONE.key)
        try:
            data = history_snapshot(command, size or PAGE_SIZE, previous)
        except (sqlite3.Error, OSError) as exc:
            logging.warning("Command history read failed: %s", exc)
            return (no_update, no_update, no_update, t('Data unavailable'), True,
                    t('History unavailable (retrying automatically)'), None, zone_label)
        if data is None:
            return (no_update,) * 8
        rows = table_rows(data["rows"], data["preferences"])
        options = [{"label": value if value else t('(empty command)'), "value": value} for value in data["commands"]]
        if command is not None and command not in data["commands"]:
            options.append({"label": command + t(' (no records)'), "value": command})
        return (options, rows, json.dumps(command),
                t('{0} of {1} commands', f"{len(data['rows']):,}", f"{data['total']:,}"),
                len(data["rows"]) >= data["total"],
                t('Updated ') + timestamp(datetime.now(TIMEZONE).timestamp(), data["preferences"]),
                data["token"], zone_label)

    @app.callback(Output('bot-runtime-status','children'),Output('bot-channel-status','children'),Output('footer-firmware','children'),Input('refresh','n_intervals'))
    def refresh_bot_state(tick):
        from meshcorestation.bridge import bridge
        from meshcorestation.config import DB_PATH
        from meshcorestation.storage.connection import connect
        from contextlib import closing
        try:
            with closing(connect(DB_PATH.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
                channel=db.execute('SELECT channel_name FROM bot_settings WHERE id=1').fetchone()[0]
        except (sqlite3.Error,OSError):return t('Bot configuration unavailable'),t('Saved channel could not be read.'),t('Companion firmware unavailable')
        from meshcorestation.config import DATA_DIR
        selected_room = None
        if (DATA_DIR / 'rooms.db').exists():
            from meshcorestation.rooms.service import RoomService
            service = RoomService(DATA_DIR / 'rooms.db')
            rid = service.bot_room()
            if rid is not None:
                selected_room = service.config(rid)
        running=bridge.status[0]=='Running'
        runtime=bridge.runtime
        parts=[runtime.device_info.get(k) for k in ('ver','fw_build')] if runtime and running else []
        firmware=t('Companion firmware ')+' · '.join(str(v) for v in parts if v) if any(parts) else t('Companion firmware unavailable')
        if selected_room:
            return (t('Running') if running and selected_room['enabled'] else t('Room disabled') if running else t('Disconnected')), (t('Bot room: ') + selected_room['name'] + (t(' (disabled)') if not selected_room['enabled'] else '')), firmware
        return (t('Running') if running and channel else t('No Bot channel selected') if running else t('Disconnected')),(t('Bot channel: ')+channel if channel else t('Select the Bot channel in Companion Channels.')),firmware
