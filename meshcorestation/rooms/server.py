"""Independent native MeshCore room endpoint using companion raw RX/TX.

No channel subscriptions, bot commands, companion identity or radio settings
are changed. The bounded worker shares only the existing serialized USB API.
"""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import os
import time
from .wire import Packet, ack, datagram, decrypt, path_length, stamp, u32


@dataclass
class Session:
    key: str
    secret: bytes
    since: int
    activity: float
    path: object = None
    pending: object = None
    failures: int = 0
    ready: float = 0


class RoomEndpoint:
    def __init__(self, service, room, clock=time.time):
        self.service, self.room, self.clock = service, room, clock
        self.identity = service.identity(room)
        self.sessions = OrderedDict()
        self.last_advert = 0
        self.received = self.sent = 0
        self.new_posts = []
        self.auth_revision = service.config(room)['auth_revision']

    def refresh_auth(self):
        config = self.service.config(self.room)
        changed = config['auth_revision'] != self.auth_revision
        if changed or not config['enabled']:
            self.sessions.clear()
        self.auth_revision = config['auth_revision']
        return config, changed

    def encode(self, packet):
        return packet.encode()

    @staticmethod
    def return_path(packet):
        # Flood paths are ordered sender -> receiver. Reverse complete hashes,
        # not individual bytes, for a direct receiver -> sender reply.
        if packet.route in (0, 1):
            size = (packet.path_code >> 6) + 1
            chunks = [packet.path[i:i+size] for i in range(0,len(packet.path),size)]
            return packet.path_code, b''.join(reversed(chunks))
        return None

    def advert(self):
        details = self.service.config(self.room)
        if not details['enabled']:
            return None
        self.last_advert = self.clock()
        return self.encode(Packet(4, self.identity.advert(details['name'], int(self.clock()))))

    def wrap(self, client, kind, clear):
        return self.encode(datagram(self.identity, bytes.fromhex(client.key), client.secret, kind, clear, client.path))

    def reply(self, packet, client, kind, clear):
        if packet.route in (0, 1):
            return self.wrap(client, 8, bytes([packet.path_code]) + packet.path + bytes([kind]) + clear)
        return self.wrap(client, kind, clear)

    def acknowledge(self, data, only=None):
        for client in self.sessions.values():
            if only is not None and client is not only:
                continue
            if client.pending and data[:4] == client.pending[0]:
                self.service.acknowledge(self.room, client.key, client.pending[1])
                client.since = client.pending[1]
                client.pending = None
                client.failures = 0
                return

    def receive(self, raw):
        packet = Packet.parse(raw)
        config, _ = self.refresh_auth()
        if not config['enabled']:
            self.sessions.clear()
            return []
        # A direct packet with remaining hops has not reached its destination.
        if packet.route in (2, 3) and packet.path:
            return []
        if packet.kind == 3:
            self.acknowledge(packet.payload)
            return []
        payload = packet.payload
        if not payload or payload[0] != self.identity.public[0]:
            return []
        if packet.kind == 7:
            if len(payload) < 51:
                return []
            key = payload[1:33].hex()
            secret = self.identity.secret(payload[1:33])
            data = decrypt(secret, payload[33:])
            if len(data) < 9:
                return []
            password = data[8:].split(b'\0',1)[0]
            role, revision = self.service.login(self.room,key,stamp(data),password)
            if revision != self.auth_revision:
                self.sessions.clear()
                self.auth_revision = revision
            client = Session(key, secret, stamp(data[4:]), self.clock(), path=self.return_path(packet), ready=self.clock()+2)
            self.sessions[key] = client
            # Local administration only; do not advertise RF administrator access.
            permissions = 1 if role == 'reader' else 2
            response = u32(int(self.clock())) + bytes([0, 0, 0, permissions]) + os.urandom(4) + b'\x01'
            return [self.reply(packet, client, 1, response)]
        if packet.kind not in (0, 2, 8) or len(payload) < 20:
            return []
        for key, client in list(self.sessions.items()):
            if bytes.fromhex(key)[0] != payload[1]:
                continue
            try:
                role = self.service.access(self.room, key)
                data = decrypt(client.secret, payload[2:])
            except PermissionError:
                self.sessions.pop(key, None)
                continue
            except ValueError:
                continue  # One-byte source hash collisions are normal.
            client.activity = self.clock()
            if packet.kind == 8:
                length = path_length(data[0])
                if len(data) < length + 2:
                    return []
                client.path = (data[0], data[1:1+length])
                if data[1+length] == 3:
                    self.acknowledge(data[2+length:], only=client)
                return []
            if len(data) < 5:
                return []
            timestamp = stamp(data)
            self.service.accept_timestamp(self.room, key, timestamp)
            if packet.kind == 2 and data[4] >> 2 == 0 and role != 'reader':
                text_bytes = data[5:].split(b'\0', 1)[0]
                text = text_bytes.decode('utf-8')
                post, created = self.service.post(self.room, key, timestamp, text, return_created=True)
                if created:
                    self.new_posts.append(post)
                self.received += 1
                client.failures = 0
                result = Packet(3, ack(data[:5]+text_bytes, bytes.fromhex(key)))
                if client.path is not None:
                    result.route, result.path_code, result.path = 2, *client.path
                return [self.encode(result)]
            if packet.kind == 0 and data[4] == 2 and packet.route in (2, 3) and client.path is not None:
                since = stamp(data[5:9])
                if since:
                    client.since = since
                client.pending = None
                client.failures = 0
                count = len(self.service.synchronize(self.room, key, client.since, 100))
                result = Packet(3, ack(data[:9], bytes.fromhex(key)) + bytes([min(count, 255)]), 2, *client.path)
                return [self.encode(result)]
            return []
        return []

    def next_push(self):
        self.refresh_auth()
        now = self.clock()
        for key, client in list(self.sessions.items()):
            try:
                self.service.access(self.room, key)
            except PermissionError:
                self.sessions.pop(key, None)
                continue
            if now - client.activity > 3600:
                self.sessions.pop(key, None)
                continue
            if client.pending and now >= client.pending[2]:
                client.pending = None
                client.failures += 1
            if client.pending or client.failures >= 3 or now < client.ready:
                continue
            posts = self.service.synchronize(self.room, key, client.since, 1)
            if not posts or posts[0]['timestamp'] + 6 > now:
                continue
            post = posts[0]
            clear = u32(post['timestamp']) + bytes([8 | (os.urandom(1)[0] & 3)]) + bytes.fromhex(post['author'])[:4] + post['text'].encode('utf-8')
            timeout = 12 if client.path is None else 4 + 2*((client.path[0]&63)+1)
            client.pending = (ack(clear, bytes.fromhex(key)), post['timestamp'], now + timeout)
            self.sessions.move_to_end(key)
            self.sent += 1
            return self.wrap(client, 2, clear)
        return None


class RoomWorker:
    def __init__(self, companion, service, on_post=None):
        self.companion, self.service = companion, service
        self.on_post = on_post
        self.queue = asyncio.Queue(maxsize=128)
        self.endpoints = OrderedDict()
        self.task = self.subscription = None
        self.error = ''
        self.dropped = 0
        self.next_send = 0

    def start(self):
        from meshcore import EventType
        self.subscription = self.companion.mc.subscribe(EventType.RX_LOG_DATA, self.on_rx)
        self.task = asyncio.create_task(self.run(), name='room-server')

    def on_rx(self, event):
        # MC 2.3.14 raw_hex includes SNR and RSSI before the RF packet.
        if not self.endpoints or self.error:
            return
        try:
            data = event.payload.get('raw_hex', '')
            raw = bytes.fromhex(data)[2:]
            if raw and ((raw[0] >> 2) & 15) in (0, 2, 3, 7, 8):
                self.queue.put_nowait(raw)
        except (ValueError, TypeError, asyncio.QueueFull):
            self.dropped += 1

    async def transmit(self, raw, endpoint):
        from meshcore import EventType
        delay = self.next_send - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        # Re-check after waiting: disabling a room must stop queued RF output.
        config, changed = endpoint.refresh_auth()
        if not config['enabled'] or changed:
            return
        result = await asyncio.wait_for(self.companion.mc.commands.send_raw_packet(raw, priority=3), 15)
        if result is None or result.type != EventType.OK:
            raise RuntimeError('Companion rejected raw packet transmission. Firmware with CMD_SEND_RAW_PACKET (65) is required.')
        self.next_send = time.monotonic() + 1.2

    def status(self):
        return dict(running=bool(self.task and not self.task.done() and not self.error),
                    error=self.error, dropped_packets=self.dropped,
                    sessions=sum(len(e.sessions) for e in self.endpoints.values()))

    async def run(self):
        try:
            while True:
                enabled = {r['id'] for r in self.service.rooms() if r['enabled']}
                for rid in set(self.endpoints) - enabled:
                    self.endpoints.pop(rid)
                for rid in sorted(enabled - set(self.endpoints)):
                    self.endpoints[rid] = RoomEndpoint(self.service, rid)
                try:
                    raw = await asyncio.wait_for(self.queue.get(), .25)
                except asyncio.TimeoutError:
                    raw = None
                for endpoint in list(self.endpoints.values()):
                    if raw:
                        try:
                            responses = endpoint.receive(raw)
                        except (ValueError, PermissionError, UnicodeError):
                            responses = []
                        for response in responses:
                            await self.transmit(response, endpoint)
                        if self.on_post and endpoint.new_posts:
                            posts, endpoint.new_posts = endpoint.new_posts, []
                            for post in posts:
                                try:
                                    await self.on_post(endpoint.room, post)
                                except Exception as exc:
                                    self.companion.logger.warning('Room bot command failed; room continues: %s', exc)
                    if time.time() - endpoint.last_advert >= 3600:
                        advert = endpoint.advert()
                        if advert:
                            await self.transmit(advert, endpoint)
                    push = endpoint.next_push()
                    if push:
                        await self.transmit(push, endpoint)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Room faults cannot unwind Runtime.session or disconnect the bot.
            self.error = str(exc)
            self.companion.logger.warning('Room server stopped; bot continues: %s', exc)
        finally:
            self.endpoints.clear()

    async def close(self):
        if self.subscription is not None:
            self.companion.mc.unsubscribe(self.subscription)
            self.subscription = None
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.endpoints.clear()
