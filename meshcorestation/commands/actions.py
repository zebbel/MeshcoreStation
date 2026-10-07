"""Explicit command actions; templates never execute code or radio commands."""
import math
import sqlite3
from dataclasses import dataclass, field


@dataclass
class Outcome:
    ok: bool
    message: str = ''
    values: dict = field(default_factory=dict)


async def execute(bot, action, message):
    if action == 'reply':
        return Outcome(True)
    if action == 'position':
        return await sender_position(bot, message['name'])
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


async def sender_position(bot, name):
    if bot.position_update_running:
        return Outcome(False, 'Position update already running; try again shortly.')
    bot.position_update_running = True
    try:
        # get_telemetry requires exactly one matching contact and waits for its reply.
        response = await bot.companion.get_telemetry(name)
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
