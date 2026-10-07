"""Companion channel operations; caller holds Companion.control_lock."""
import base64
import hashlib
import hmac
import json
import re
import secrets

from meshcore import EventType
from meshcorestation.radio.contacts_control import public_key

PUBLIC_SECRET = bytes.fromhex('8b3387e9c5cdea6ac9e5edbaa115cd72')
REVISION_KEY = secrets.token_bytes(32)


def channel_type(name, secret):
    if secret == PUBLIC_SECRET:
        return 'public'
    if name.startswith('#') and secret == hashlib.sha256(name.encode('utf-8')).digest()[:16]:
        return 'hashtag'
    return 'private'


async def read_channels(companion):
    info = await companion.get_self_info()
    identity = public_key((info or {}).get('public_key'))
    result = await companion.mc.commands.send_device_query()
    if result is None or result.type != EventType.DEVICE_INFO or not isinstance(result.payload, dict):
        raise RuntimeError('Could not read channel capacity. Refresh before retrying.')
    capacity = result.payload.get('max_channels')
    if type(capacity) is not int or not 1 <= capacity <= 255:
        raise RuntimeError('Firmware did not report a valid channel capacity.')
    slots, channels = [], []
    for index in range(capacity):
        result = await companion.mc.commands.get_channel(index)
        if result is None or result.type != EventType.CHANNEL_INFO or not isinstance(result.payload, dict):
            raise RuntimeError('Could not read every channel slot. Refresh before retrying.')
        item = result.payload
        name, secret = item.get('channel_name'), item.get('channel_secret')
        if (type(item.get('channel_idx')) is not int or item['channel_idx'] != index
                or not isinstance(name, str) or not isinstance(secret, bytes) or len(secret) != 16):
            raise RuntimeError('Incomplete channel response. Refresh before retrying.')
        slots.append((name, secret))
        if name or secret != bytes(16):
            channels.append({'index': index, 'name': name, 'type': channel_type(name, secret), 'protected': index == companion.channel_idx})
    # Keyed revisions detect changes to keys without disclosing keys or their hashes.
    state = [identity, companion.channel_idx, [(n, s.hex()) for n, s in slots]]
    revision = hmac.new(REVISION_KEY, json.dumps(state).encode(), hashlib.sha256).hexdigest()
    return {'public_key': identity, 'revision': revision, 'capacity': capacity,
            'free_slots': sum(n == '' and s == bytes(16) and i != companion.channel_idx
                              for i, (n, s) in enumerate(slots)), 'channels': channels}, slots


def new_channel(value):
    if not isinstance(value, dict) or set(value) - {'name', 'type', 'secret'}:
        raise ValueError('Invalid channel fields')
    kind, name = value.get('type'), value.get('name')
    if kind not in {'public', 'hashtag', 'private'}:
        raise ValueError('Choose Public, Hashtag or Private')
    if not isinstance(name, str):
        raise ValueError('Channel needs a name')
    name = name.strip()
    if kind == 'hashtag' and not name.startswith('#'):
        name = '#' + name
    if (not name or name == '#' or len(name.encode('utf-8')) > 31
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError('Name must contain 1–31 UTF-8 bytes without control characters')
    if kind == 'public':
        secret = PUBLIC_SECRET
    elif kind == 'hashtag':
        secret = hashlib.sha256(name.encode('utf-8')).digest()[:16]
    else:
        if name.startswith('#'):
            raise ValueError('Use Hashtag for names starting with #')
        raw = value.get('secret')
        if not isinstance(raw, str):
            raise ValueError('Private channel needs a 16-byte key (hex or base64)')
        raw = raw.strip()
        try:
            secret = bytes.fromhex(raw) if re.fullmatch(r'[0-9a-fA-F]{32}', raw) else base64.b64decode(raw, validate=True)
        except ValueError:
            raise ValueError('Invalid private channel key') from None
        if len(secret) != 16 or secret in (bytes(16), PUBLIC_SECRET):
            raise ValueError('Use a nonzero 16-byte private key; use Public for the public key')
    return name, secret


async def handle_channels(companion, request):
    operation = request.get('operation')
    if operation not in {'get_channels', 'add_channel', 'delete_channel', 'set_bot_channel'}:
        raise ValueError('Unknown channel operation')
    before, slots = await read_channels(companion)
    if operation == 'get_channels':
        return {'ok': True, **before}
    if (request.get('expected_public_key') != before['public_key'] or request.get('expected_revision') != before['revision']):
        return {'ok': False, 'error': 'Channels or companion changed. Refresh before saving.', **before}
    if operation == 'set_bot_channel':
        index = request.get('index')
        if type(index) is not int or not 0 <= index < len(slots):
            raise ValueError('Invalid channel slot')
        name, secret = slots[index]
        if not name or sum(n.strip().casefold() == name.strip().casefold() for n, _ in slots) != 1:
            raise ValueError('Bot channel needs a nonempty, unique name')
        # Caller holds control_lock, so an in-flight reply completes before switching.
        companion.database.set_bot_channel(name)
        companion.channel_idx = index
        companion.channel_name = name
        companion.channel_hash = hashlib.sha256(secret).digest()[:1].hex()
        companion.recent_rx_logs.clear()
        after, _ = await read_channels(companion)
        return {'ok': True, **after}
    if operation == 'add_channel':
        name, secret = new_channel(request.get('value'))
        if any(n.casefold() == name.casefold() or s == secret for n, s in slots):
            raise ValueError('A channel with this name or key already exists')
        index = next((i for i, (n, s) in enumerate(slots) if n == '' and s == bytes(16) and i != companion.channel_idx), None)
        if index is None:
            raise ValueError('No empty channel slots available')
    else:
        index = request.get('index')
        if type(index) is not int or not 0 <= index < len(slots):
            raise ValueError('Invalid channel slot')
        if request.get('confirm_delete') is not True:
            raise ValueError('Confirm channel deletion first')
        if index == companion.channel_idx:
            raise ValueError('This channel is used by the running bot and cannot be deleted')
        if slots[index] == ('', bytes(16)):
            raise ValueError('Channel no longer exists. Refresh the list.')
        name, secret = '', bytes(16)
    result = await companion.mc.commands.set_channel(index, name, secret)
    if result is None or result.type != EventType.OK:
        raise RuntimeError('Channel change was not acknowledged. Refresh before retrying.')
    after, saved = await read_channels(companion)
    wanted = list(slots)
    wanted[index] = (name, secret)
    verified = after['public_key'] == before['public_key'] and saved == wanted
    response = {'ok': verified, **after}
    if not verified:
        response['error'] = 'Channel change could not be verified. Refresh before retrying.'
    companion.logger.info('Companion channel operation %s: slot=%s verified=%s', operation, index, verified)
    return response
