"""Small, explicit placeholder language. Never evaluates Python or expressions."""
import math
import re
import string
from dataclasses import dataclass

# name: (group, description, example, decimal places; None means text/integer)
CATALOG = {
    'sender_name': ('Sender', 'Sender name', 'Alice', None),
    'sender_public_key': ('Sender', 'Saved sender key, when uniquely known', 'ab' * 32, None),
    'command': ('Message', 'Received command', 'ping', None),
    'arguments': ('Message', 'Text following the command', 'example', None),
    'hop_count': ('Connection', 'Received hop count', 2, None),
    'path': ('Connection', 'Received route', '2 hops [32:e5]', None),
    'rssi': ('Connection', 'Received RSSI, without dBm', -92, None),
    'snr': ('Connection', 'Received SNR, without dB', 7.5, 1),
    'direct_distance': ('Distance', 'Straight-line distance in km, without units', 12.34, 2),
    'route_distance': ('Distance', 'Route distance in km; ~ estimated, >= lower bound', 18.76, 2),
    'node_name': ('Companion', 'Connected companion name', 'MeshcoreStation', None),
    'node_public_key': ('Companion', 'Connected companion public key', 'cd' * 32, None),
    'battery_voltage': ('Battery', 'Companion voltage, without V', 3.86, 2),
    'battery_percent': ('Battery', 'Approximate 1S LiPo charge, without %', 52, None),
    'uptime': ('Status', 'Companion uptime', '2d6h', None),
    'queue_length': ('Status', 'Companion transmit queue', 0, None),
    'error_count': ('Status', 'Companion error count/flags when reported', 0, None),
    'noise_floor': ('Radio', 'Companion noise floor, without dBm', -118, None),
    'packets_received': ('Radio', 'Companion received packets', 864, None),
    'packets_sent': ('Radio', 'Companion sent packets', 124, None),
    'repeater_count': ('Network', 'Repeaters in SQLite', 42, None),
    'channel_name': ('Network', 'Bot channel name', 'meshcorestation', None),
    'scope_name': ('Network', 'Scope matched to the received packet', 'rhein-neckar', None),
    'date': ('Time', 'Current date in Europe/Berlin', '07.10.2026', None),
    'time': ('Time', 'Current time in Europe/Berlin', '08:45:00', None),
    'command_list': ('Help', 'Configured commands and their help text', '', None),
    'latitude': ('Action', 'Retrieved sender latitude in degrees', 49.1234, 4),
    'longitude': ('Action', 'Retrieved sender longitude in degrees', 8.4567, 4),
    'altitude': ('Action', 'Retrieved sender altitude in metres', 123, 1),
    'added_scope': ('Action', 'Requested scope name', 'rhein-neckar', None),
    'result': ('Action', 'Action success or failure explanation', 'Position updated and saved.', None),
}
NUMERIC = {name for name, item in CATALOG.items() if isinstance(item[2], (int, float))}
MAX_COMMANDS, MAX_TEMPLATE_BYTES, MAX_REPLY_BYTES = 24, 512, 4096


@dataclass(frozen=True)
class Distance:
    value: float
    qualifier: str = ''


def fields(template):
    if not isinstance(template, str) or not template.strip() or len(template.encode()) > MAX_TEMPLATE_BYTES:
        raise ValueError(f'Reply template must contain 1–{MAX_TEMPLATE_BYTES} UTF-8 bytes.')
    if re.search(r'[\x00-\x08\x0b-\x1f\x7f]', template):
        raise ValueError('Reply contains unsupported control characters.')
    found = set()
    try:
        parts = list(string.Formatter().parse(template))
    except ValueError:
        raise ValueError('Unmatched braces. Use {{ and }} for literal braces.') from None
    for _, name, spec, conversion in parts:
        if name is None:
            continue
        if name not in CATALOG:
            raise ValueError('Unknown placeholder: {' + name + '}')
        if conversion or (spec and (name not in NUMERIC or not re.fullmatch(r'\.[0-4]f', spec))):
            raise ValueError('Only numeric formatting such as {snr:.1f} is supported.')
        found.add(name)
    return found


def render(template, data):
    fields(template)
    pieces = []
    for literal, name, spec, _ in string.Formatter().parse(template):
        pieces.append(literal)
        if name is None:
            continue
        value, prefix = data.get(name), ''
        if isinstance(value, Distance):
            value, prefix = value.value, value.qualifier
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            pieces.append('unknown'); continue
        if name in NUMERIC:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                pieces.append('unknown'); continue
            decimals = CATALOG[name][3]
            value = format(value, spec or (f'.{decimals}f' if decimals is not None else 'g'))
        # Inserted values are plain text, never recursively expanded.
        pieces.append(prefix + str(value))
    result = ''.join(pieces)
    if len(result.encode()) > MAX_REPLY_BYTES:
        raise ValueError('Expanded reply is too long. Shorten the template or help texts.')
    return result


def command_list(commands):
    return ' | '.join(f"{item['trigger']}{' add <name>' if item.get('action') == 'scope' else ''}: {item['help']}" for item in commands)


def example_data(commands):
    return {**{name: item[2] for name, item in CATALOG.items()}, 'command_list': command_list(commands)}


def public_catalog():
    return [{'name': name, 'group': item[0], 'description': item[1], 'numeric': name in NUMERIC, 'decimals': item[3]} for name, item in CATALOG.items()]


def split_reply(text, limit=120):
    """Bound UTF-8 bytes per radio message without cutting a character."""
    parts, current, size = [], [], 0
    for char in text:
        length = len(char.encode())
        if size + length > limit:
            parts.append(''.join(current)); current, size = [], 0
        current.append(char); size += length
    if current:
        parts.append(''.join(current))
    return parts
