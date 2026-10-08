"""Explicit command actions; templates never execute code or radio commands."""
import math
import re
import sqlite3
from dataclasses import dataclass, field


@dataclass
class Outcome:
    ok: bool
    message: str = ''
    values: dict = field(default_factory=dict)


async def execute(bot, action, message, matched_rx=None):
    if action == 'reply':
        return Outcome(True)
    if action == 'position':
        parts = message['message'].strip().split(maxsplit=1)
        return await sender_position(bot, message['name'], matched_rx, parts[1] if len(parts) > 1 else '')
    if action == 'scope':
        args = message['message'].strip().split(maxsplit=1)
        name = args[1].strip() if len(args) > 1 else ''
        # Preserve the previous "scope add <name>" syntax, including renamed commands.
        parts = name.split(maxsplit=1)
        if parts and parts[0].casefold() == 'add':
            name = parts[1].strip() if len(parts) > 1 else ''
        if not name:
            return Outcome(False, f"Usage: {args[0]} add <name>")
        try:
            name, added = bot.database.add_scope(name)
            return Outcome(added, f"Scope {name} added." if added else f"Scope {name} already exists.", {'added_scope': name})
        except ValueError as exc:
            return Outcome(False, str(exc))
        except sqlite3.Error as exc:
            bot.logger.warning('Scope database error: %s', exc)
            return Outcome(False, 'Could not save scope; check the bot log.')
    return Outcome(False, 'Unknown command action.')


def parse_coordinates(arguments):
    number = r'[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)'
    match = re.fullmatch(r'\s*('+number+r')(?:\s*,\s*|\s+)('+number+r')\s*', arguments)
    if not match:
        raise ValueError('Use latitude, longitude in decimal degrees, for example 49.123456, 8.654321.')
    lat, lon = map(float, match.groups())
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180 or (lat,lon)==(0,0):
        raise ValueError('Invalid coordinates: latitude must be -90 to 90 and longitude -180 to 180; 0,0 is treated as unavailable.')
    return lat, lon


async def sender_position(bot, name, matched_rx=None, arguments=''):
    if bot.position_update_running:
        return Outcome(False, 'Position update already running; try again shortly.')
    bot.position_update_running = True
    try:
        if arguments.strip():
            try:
                lat, lon = parse_coordinates(arguments)
            except ValueError as exc:
                return Outcome(False, f'{exc} Saved position unchanged.')
            contact = await bot.companion.get_sender_contact(name)
            if contact is None:
                return Outcome(False, 'Sender contact is unknown or ambiguous; saved position unchanged.')
            bot.database.save_companion_position(contact['public_key'], contact['adv_name'], lat, lon, None)
            return Outcome(True, f'Position saved: {lat:.6f}, {lon:.6f}.', {'latitude':lat,'longitude':lon,'altitude':None,'sender_public_key':contact['public_key']})
        scope_name, _ = bot.companion._get_reply_scope(matched_rx)
        if scope_name is None:
            return Outcome(False, 'Request scope is unknown; telemetry was not requested.')
        from meshcorestation.commands.templates import split_reply
        acknowledgment = f"@[{name}] | Position request received. Requesting telemetry…"
        for part in split_reply(acknowledgment):
            sent = await bot.companion.send_channel_message(bot.companion.channel_idx, part, matched_rx)
            if sent is False or sent != scope_name:
                return Outcome(False, 'Could not send the position acknowledgment; telemetry was not requested.')
        # Await radio acceptance of the acknowledgment before requesting telemetry.
        response = await bot.companion.get_telemetry(name, matched_rx)
        if response is None:
            return Outcome(False, 'Could not retrieve telemetry; contact unknown, ambiguous, unavailable or telemetry denied. Saved position unchanged.')
        gps = next((item.get('value') for item in response['telemetry'] if item.get('type') == 'gps' and item.get('channel') == 1), None)
        if not isinstance(gps, dict):
            return Outcome(False, 'No GPS position in telemetry; saved position unchanged.')
        lat, lon = float(gps['latitude']), float(gps['longitude'])
        alt = float(gps['altitude']) if gps.get('altitude') is not None else None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (alt is not None and not math.isfinite(alt)):
            return Outcome(False, 'Invalid GPS coordinates; saved position unchanged.')
        contact = response['contact']
        bot.database.save_companion_position(contact['public_key'], contact['adv_name'], lat, lon, alt)
        return Outcome(True, 'Position updated and saved.', {'latitude': lat, 'longitude': lon, 'altitude': alt, 'sender_public_key': contact['public_key']})
    except Exception as exc:
        bot.logger.warning('Position action failed: %s %s', type(exc).__name__, exc)
        return Outcome(False, 'Position update failed; saved position unchanged.')
    finally:
        bot.position_update_running = False
