"""Serialized remote exchanges; bind replies to the selected repeater identity."""
import asyncio
import time
import logging
import string
from meshcore import EventType

TIMEOUT = 30


class RepeaterTransport:
    def __init__(self, companion):
        self.companion = companion
        self.last_send = 0
        self.sequence = 0
        # MeshCore debug logging includes raw frames and password echoes.
        logging.getLogger("meshcore").setLevel(logging.WARNING)
        self.blocked_until = {}

    async def contact(self, key):
        result = await self.companion.mc.commands.get_contacts()
        if result is None or result.type != EventType.CONTACTS or not isinstance(result.payload, dict):
            raise ValueError('Could not read companion contacts.')
        matches = [c for c in result.payload.values() if isinstance(c, dict) and str(c.get('public_key', '')).lower().startswith(key[:12])]
        if len(matches) != 1 or str(matches[0].get('public_key', '')).lower() != key or matches[0].get('type') != 2:
            raise ValueError('Select one unambiguous repeater contact. Refresh Contacts.')
        return matches[0]

    async def login(self, contact, password):
        try:
            event = await asyncio.wait_for(self.companion.mc.commands.send_login_sync(contact, password, timeout=TIMEOUT), TIMEOUT + 10)
        except asyncio.TimeoutError:
            raise ValueError('Login timed out. Check password, route and repeater availability.') from None
        if event is None or event.type != EventType.LOGIN_SUCCESS:
            raise ValueError('No successful login reply. Check password, route and repeater availability.')
        payload = event.payload or {}
        if str(payload.get('pubkey_prefix', '')).lower() != contact['public_key'][:12].lower():
            raise ValueError('Login reply did not match the selected repeater.')
        return payload

    async def cli(self, contact, command, expect_reply=True):
        """Register before sending; no automatic retry of commands or writes."""
        key = contact['public_key'].lower()
        if time.monotonic() < self.blocked_until.get(key, 0):
            raise ValueError('A previous CLI response timed out. Wait two minutes before reading again.')
        # Repeater replay protection needs distinct sender timestamps. Waiting,
        # rather than incrementing a future timestamp, keeps companion login valid.
        delay = self.last_send + 1.05 - time.time()
        if delay > 0:
            await asyncio.sleep(delay)
        alphabet = string.ascii_letters + string.digits
        self.sequence = (self.sequence + 1) % (len(alphabet) ** 2)
        tag = alphabet[self.sequence // len(alphabet)] + alphabet[self.sequence % len(alphabet)] + '|'
        future = asyncio.get_running_loop().create_future()
        async def receive(event):
            payload = event.payload or {}
            if (not future.done() and str(payload.get('pubkey_prefix', '')).lower() == key[:12]
                    and payload.get('txt_type') in (0, 1) and isinstance(payload.get('text'), str)):
                text = payload['text'].strip()
                # Repeater CLI reflects the two-character request prefix. Ignore
                # late replies and ordinary direct messages, even from this node.
                if text.startswith(tag):
                    future.set_result(text[len(tag):].strip())
        subscription = self.companion.mc.subscribe(EventType.CONTACT_MSG_RECV, receive)
        try:
            self.last_send = time.time()
            sent = await self.companion.mc.commands.send_cmd(contact, tag + command, timestamp=int(self.last_send))
            if sent is None or sent.type != EventType.MSG_SENT:
                raise ValueError('Companion did not confirm sending the command.')
            if not expect_reply:
                return 'Command sent; execution is not confirmed. Refresh status after the repeater reconnects.'
            return await asyncio.wait_for(future, TIMEOUT)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Back off after missing replies; never automatically repeat a write.
            self.blocked_until[key] = time.monotonic() + 120
            raise
        finally:
            subscription.unsubscribe()
            if not future.done():
                future.cancel()
