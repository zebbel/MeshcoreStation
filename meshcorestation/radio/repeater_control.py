"""Repeater sessions and management operations, owned by the radio event loop."""
import asyncio
import re
import secrets
import time
from meshcorestation.radio.neighbor_names import with_neighbor_names
from meshcorestation.radio.repeater_fields import FIELDS, validate, parse_value
from meshcorestation.radio.repeater_transport import RepeaterTransport, TIMEOUT


class RepeaterControl:
    def __init__(self, companion):
        self.companion = companion
        self.transport = RepeaterTransport(companion)
        self.sessions = {}

    async def execute(self, request):
        # Session tokens never go into the database or application logs.
        now = time.monotonic()
        self.sessions = {k: v for k, v in self.sessions.items() if v['expires'] > now}
        action, key = request.get('action'), request.get('public_key', '')
        if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
            raise ValueError('Invalid repeater key.')
        if action == 'logout':
            self.sessions.pop(request.get('session', ''), None)
            return {'ok': True}
        contact = await self.transport.contact(key)
        if action == 'login':
            password = request.get('password', '')
            if not isinstance(password, str) or len(password.encode()) > 15 or re.search(r'[\x00-\x1f\x7f]', password):
                raise ValueError('Password must be at most 15 UTF-8 bytes without control characters.')
            login = await self.transport.login(contact, password)
            token = secrets.token_urlsafe(32)
            if len(self.sessions) >= 16:
                self.sessions.pop(next(iter(self.sessions)))
            self.sessions[token] = {'key': key, 'expires': now + 900, 'values': {}}
            return {'ok': True, 'session': token, 'admin': login.get('is_admin') is True, 'contact': self.identity(contact), 'fields': FIELDS}
        token = request.get('session', '')
        session = self.sessions.get(token)
        if not session or session['key'] != key:
            return {'ok': False, 'expired': True, 'error': 'Management session expired. Connect again.'}
        session['expires'] = now + 900
        # Blank login asks for the companion's current ACL rights. It does not
        # overwrite an admin login with guest credentials, including after monitoring.
        login = await self.transport.login(contact, '')
        admin = login.get('is_admin') is True
        commands = self.companion.mc.commands
        try:
            if action in {'status', 'telemetry', 'neighbors', 'acl'}:
                if action == 'acl' and not admin:
                    raise ValueError('Administrator access is required.')
                if action == 'status':
                    data = await commands.req_status_sync(contact, timeout=TIMEOUT)
                    if data and str(data.get('pubkey_pre', '')).lower() != key[:12]:
                        raise ValueError('Status identity did not match.')
                elif action == 'telemetry':
                    data = await commands.req_telemetry_sync(contact, timeout=TIMEOUT)
                elif action == 'neighbors':
                    data = await commands.req_neighbours_sync(contact, count=15, offset=request.get('offset', 0), timeout=TIMEOUT)
                else:
                    data = await commands.req_acl_sync(contact, timeout=TIMEOUT)
                if data is None:
                    raise ValueError('No response. The repeater may be unreachable or this feature may be unsupported.')
                if action == 'neighbors':
                    data = with_neighbor_names(self.companion.database.db, data)
                return {'ok': True, 'data': data, 'sampled_at': time.time(), 'admin': admin, 'contact': self.identity(contact), 'firmware_level': login.get('fw_ver_level')}
            if not admin:
                raise ValueError('Administrator access is required to read or change configurations.')
            if action == 'read':
                field = request.get('field')
                if field not in FIELDS or FIELDS[field]['kind'] == 'password':
                    raise ValueError('This field cannot be read.')
                value = parse_value(field, await self.transport.cli(contact, 'get ' + field))
                session['values'][field] = value
                return {'ok': True, 'field': field, 'value': value}
            if action == 'write':
                field = request.get('field')
                if field not in FIELDS:
                    raise ValueError('Unknown field.')
                value = validate(field, request.get('value'))
                if request.get('confirm') is not True:
                    raise ValueError('Review and confirm the change first.')
                secret = FIELDS[field]['kind'] == 'password'
                if not secret:
                    if field not in session['values'] or request.get('expected') != session['values'][field]:
                        raise ValueError('Read this section before saving.')
                    current = parse_value(field, await self.transport.cli(contact, 'get ' + field))
                    if current != request['expected']:
                        session['values'].pop(field, None)
                        raise ValueError('This setting changed on the repeater. Read the section again.')
                prefix = FIELDS[field].get('write', 'set ' + field)
                reply = await self.transport.cli(contact, prefix + ' ' + value)
                # Admin password replies echo the password; never send that echo to HTTP.
                accepted = reply.lower().startswith(('ok', '(ok')) or (field == 'admin_password' and reply.startswith('password now:'))
                if not accepted:
                    raise ValueError('Repeater rejected the change.' if secret else 'Repeater reply: ' + reply[:200])
                if secret:
                    return {'ok': True, 'field': field, 'value': '', 'message': 'Password change acknowledged.'}
                session['values'].pop(field, None)
                actual = parse_value(field, await self.transport.cli(contact, 'get ' + field))
                session['values'][field] = actual
                return {'ok': True, 'field': field, 'value': actual, 'message': 'Saved and read back.' if actual == value else 'Repeater returned a different value. Review the applied value.', 'reboot_required': 'reboot' in reply.lower()}
            if action == 'action':
                name = request.get('name')
                if name not in {'advert', 'clock_sync', 'reboot'} or request.get('confirm') is not True:
                    raise ValueError('Unknown or unconfirmed action.')
                command = 'time ' + str(int(time.time())) if name == 'clock_sync' else name
                reply = await self.transport.cli(contact, command, expect_reply=name != 'reboot')
                if name == 'reboot':
                    self.sessions.pop(token, None)
                elif not reply.lower().startswith(('ok', '(ok')):
                    raise ValueError('Repeater reply: ' + reply[:200])
                return {'ok': True, 'message': reply, 'expired': name == 'reboot'}
            if action == 'regions_read':
                return {'ok': True, 'data': await self.transport.cli(contact, 'region')}
            if action == 'region':
                verb = request.get('verb')
                if verb not in {'put', 'remove', 'allowf', 'denyf', 'home', 'default'} or request.get('confirm') is not True:
                    raise ValueError('Confirm a valid region operation.')
                region = self.region_name(request.get('name'))
                command = 'region ' + verb + ' ' + region
                if verb == 'put':
                    command += ' ' + self.region_name(request.get('parent') or '*')
                reply = await self.transport.cli(contact, command)
                if not reply.lower().startswith(('ok', 'home is now ', 'default scope is now ')):
                    raise ValueError('Region reply: ' + reply[:200])
                saved = await self.transport.cli(contact, 'region save')
                if not saved.lower().startswith('ok'):
                    raise ValueError('Region changed, but persistence could not be confirmed: ' + saved[:160])
                return {'ok': True, 'message': 'Region change acknowledged and saved. Read regions to review.'}
            if action == 'permission':
                target, permission = request.get('target', ''), request.get('permission')
                if not isinstance(target, str) or not re.fullmatch('[0-9a-fA-F]{64}', target) or permission not in ('0', '1', '2', '3') or request.get('confirm') is not True:
                    raise ValueError('Enter a full companion public key and confirm its permission change.')
                reply = await self.transport.cli(contact, 'setperm ' + target + (' ' + permission))
                if not reply.lower().startswith('ok'):
                    raise ValueError('Permission reply: ' + reply[:200])
                return {'ok': True, 'message': 'Permission change acknowledged. Read permissions to review.'}
            raise ValueError('Unknown repeater operation.')
        except asyncio.TimeoutError:
            session['values'].clear()
            raise ValueError('Repeater response timed out. A submitted change may have applied. Wait two minutes, then read before retrying.') from None

    @staticmethod
    def region_name(value):
        if not isinstance(value, str) or not re.fullmatch(r'\*|#?[A-Za-z0-9_-]{1,30}', value):
            raise ValueError('Use a region name of 1–30 letters, digits, hyphens or underscores, or *.')
        # Hashtags affect region keys: preserve the actual wire name exactly.
        return value

    @staticmethod
    def identity(contact):
        return {k: contact.get(k) for k in ('public_key', 'adv_name', 'out_path_len')}
