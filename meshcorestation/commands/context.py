"""Collect only the values needed by a reply, without guessing missing readings."""
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from meshcorestation.commands.templates import Distance, command_list

STATS = {'battery_voltage', 'battery_percent', 'uptime', 'queue_length', 'error_count', 'noise_floor', 'packets_received', 'packets_sent'}
IDENTITY = {'node_name', 'node_public_key', 'direct_distance', 'route_distance'}
CURVE = [(3.0, 0), (3.3, 2), (3.5, 5), (3.6, 10), (3.7, 20), (3.75, 30), (3.8, 40), (3.85, 50), (3.9, 60), (3.95, 70), (4.0, 80), (4.1, 90), (4.2, 100)]


def finite(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def percent(voltage):
    if voltage is None or not 3.0 <= voltage <= 4.2:
        return None
    for (v0, p0), (v1, p1) in zip(CURVE, CURVE[1:]):
        if voltage <= v1:
            return int(p0 + (voltage - v0) / (v1 - v0) * (p1 - p0) + 0.5)


async def collect(bot, needed, message, rx, commands, result=None):
    companion, db = bot.companion, bot.database
    parts = message['message'].strip().split(maxsplit=1)
    now = datetime.now(ZoneInfo('Europe/Berlin'))
    values = dict(sender_name=message.get('name'), command=parts[0].casefold() if parts else '', arguments=parts[1] if len(parts) > 1 else '',
                  hop_count=companion._get_message_hops(message), path=bot._format_rx_path(rx) if rx else message.get('path'),
                  rssi=finite(rx.get('rssi')) if rx else None, snr=finite(rx.get('snr')) if rx else None,
                  channel_name=companion.channel_name, date=now.strftime('%d.%m.%Y'), time=now.strftime('%H:%M:%S'), result=result)
    if 'command_list' in needed:
        values['command_list'] = command_list(commands)
    if 'repeater_count' in needed:
        values['repeater_count'] = db.get_repeater_count()
    if 'scope_name' in needed:
        try:
            values['scope_name'] = companion._get_reply_scope(rx)[0]
        except (ValueError, TypeError, KeyError):
            values['scope_name'] = None
    own = {}
    if needed & IDENTITY:
        try:
            own = await companion.get_self_info() or {}
        except Exception:
            bot.logger.warning('Command placeholder: companion identity unavailable.')
        values.update(node_name=own.get('name'), node_public_key=own.get('public_key'))
    if needed & STATS:
        try:
            core, radio, packets = await companion.get_status()
            get = bot._get_value
            mv = finite(get(core, 'battery_mv', 'battery'))
            voltage = mv / 1000 if mv is not None else None
            uptime = finite(get(core, 'uptime_secs', 'uptime'))
            values.update(battery_voltage=voltage, battery_percent=percent(voltage), uptime=bot._format_uptime(uptime) if uptime is not None else None,
                          queue_length=finite(get(core, 'queue_len', 'queue')), error_count=finite(get(core, 'errors', 'error_flags')),
                          noise_floor=finite(get(radio, 'noise_floor')), packets_received=finite(get(packets, 'packets_received', 'packets_recv', 'recv', 'rx')),
                          packets_sent=finite(get(packets, 'packets_sent', 'sent', 'tx')))
        except Exception:
            bot.logger.warning('Command placeholder: companion statistics unavailable.')
    if needed & {'sender_public_key', 'direct_distance', 'route_distance'}:
        positions = db.get_companion_positions_by_name(message.get('name', ''))
        if len(positions) == 1:
            sender = positions[0]
            values['sender_public_key'] = sender['public_key']
            start, end = bot._valid_position(sender['latitude'], sender['longitude']), bot._valid_position(own.get('adv_lat'), own.get('adv_lon'))
            if start and end:
                values['direct_distance'] = bot._distance_km(*start, *end)
                # Reuse the existing path resolution and geographic uncertainty rules.
                route = bot._get_route_distance_text(start, end, message, rx)
                parsed = re.match(r'Route (~|>=)?(\d+(?:\.\d+)?) km', route)
                if parsed:
                    values['route_distance'] = Distance(float(parsed[2]), parsed[1] or '')
    return values
