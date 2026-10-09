"""Private MCOD OLED extension over the existing, serialized USB connection."""
import asyncio
import math
import os
import struct
import time
import unicodedata
from meshcorestation.commands.context import percent
from meshcorestation.storage.voltage_store import config, latest

MAGIC = b'\xf0MCOD\x01'


class DisplayError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'OLED command failed (status {status})')


class DisplayTransport:
    def __init__(self, companion):
        self.companion = companion
        self.original = companion.mc._reader
        self.pending = None
        self.request_id = 0
        companion.mc.connection_manager.set_reader(self)

    async def handle_rx(self, data):
        data = bytes(data)
        if data.startswith(MAGIC):
            if self.pending and len(data) >= 9:
                request_id, operation, future = self.pending
                if data[6:8] == bytes([request_id, operation]) and not future.done():
                    future.set_result(data)
            return
        # A stock companion can reject INFO with a standard unsupported error.
        # No other serial command is outstanding while our shared lock is held.
        if self.pending and data[:1] == b'\x01':
            future = self.pending[2]
            if not future.done():
                future.set_exception(DisplayError(3))
            return
        await self.original.handle_rx(data)

    async def command(self, operation, arguments=b''):
        async with self.companion.serial_command_lock:
            self.request_id = (self.request_id + 1) % 256
            future = asyncio.get_running_loop().create_future()
            self.pending = (self.request_id, operation, future)
            try:
                await self.companion.mc.connection_manager.send(MAGIC + bytes([self.request_id, operation]) + arguments)
                reply = await asyncio.wait_for(future, 2)
                if reply[8]:
                    raise DisplayError(reply[8])
                return reply[9:]
            finally:
                self.pending = None
                if not future.done():
                    future.cancel()

    def detach(self):
        self.companion.mc.connection_manager.set_reader(self.original)


def ascii_text(value, length=21):
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'replace').decode()
    return ''.join(ch if 32 <= ord(ch) <= 126 else ' ' for ch in value)[:length] or '-'


def scene(db, now):
    cfg = config(db)
    sample = latest(db, cfg)
    name = db.execute('SELECT name FROM repeaters WHERE lower(public_key)=?', (cfg['public_key'],)).fetchone()
    name = name['name'] if name else cfg['public_key'][:12]
    texts = [(0, 0, ascii_text(name if cfg['public_key'] else 'Select battery node'))]
    valid = sample and type(sample['voltage']) in (int, float) and math.isfinite(sample['voltage'])
    if valid:
        voltage = sample['voltage']
        estimate = percent(voltage)
        age = now - sample['sampled_at']
        suffix = ' stale' if age > max(120, cfg['interval_minutes'] * 120) else ''
        texts.append((0, 10, ascii_text(f'{voltage:.2f}V ' + (f'~{estimate}%' if estimate is not None else '--%') + suffix)))
    else:
        texts.append((0, 10, 'No current reading'))
    rows = db.execute('''SELECT sampled_at,voltage,interval_seconds FROM voltage_samples
        WHERE public_key=? AND voltage_channel=? AND sampled_at>=? AND sampled_at<=?
        ORDER BY sampled_at,id''', (cfg['public_key'], cfg['voltage_channel'], now - 86400, now)).fetchall()
    # At most one point per display column; preserve failures and time gaps.
    runs, current = [], []
    previous = None
    for row in rows:
        v, stamp = row['voltage'], row['sampled_at']
        if v is None or not math.isfinite(v):
            if current:
                runs.append(current)
            current, previous = [], None
            continue
        if previous is not None and stamp - previous > max(120, row['interval_seconds'] * 2):
            if current:
                runs.append(current)
            current = []
        x = 1 + round((stamp - (now - 86400)) / 86400 * 125)
        if current and current[-1][0] == x:
            current[-1] = (x, v)
        else:
            current.append((x, v))
        previous = stamp
    if current:
        runs.append(current)
    values = [v for run in runs for _, v in run]
    if not values:
        texts += [(0, 32, 'No 24h history'), (0, 56, '-24h'), (108, 56, 'now')]
        return texts, []
    low, high = 3.0, 4.2
    texts += [(0, 56, ascii_text(f'24h {low:.2f}-{high:.2f}V', 17)), (108, 56, 'now')]
    points = [[(x, max(24, min(51, 51 - round((v - low) / (high - low) * 27)))) for x, v in run] for run in runs]
    return texts, points


class OledDisplay:
    def __init__(self, companion):
        self.companion = companion
        self.transport = None
        self.task = None
        self.acquired = False

    def start(self):
        if os.getenv('MESHCORESTATION_OLED', '1').lower() not in ('0', 'false', 'off'):
            self.transport = DisplayTransport(self.companion)
            self.task = asyncio.create_task(self.run(), name='companion-oled')

    async def draw(self, graphics):
        texts, runs = scene(self.companion.database.db, time.time())
        send = self.transport.command
        # BEGIN clears pending content and renews the lease, including after an
        # expired lease. Never retry append operations after an uncertain reply.
        await send(1, struct.pack('<H', 60))
        self.acquired = True
        for x, y, text in texts:
            if not graphics and y == 32:
                continue
            await send(2, bytes([x, y, 1]) + text.encode('ascii'))
        if graphics:
            flags, capacity, max_points = graphics
            segments = 0
            if flags & 1:
                for line in ((0, 24, 0, 53), (0, 53, 127, 53)):
                    if segments < capacity:
                        await send(8, bytes(line))
                        segments += 1
            for run in runs:
                if len(run) == 1:
                    if flags & 1 and segments < capacity:
                        await send(8, bytes(run[0] + run[0]))
                        segments += 1
                    continue
                offset = 0
                while offset < len(run) - 1 and segments < capacity:
                    if flags & 2 and max_points >= 2:
                        chunk = run[offset:offset + min(max_points, capacity - segments + 1)]
                        await send(9, bytes([len(chunk)]) + bytes(v for point in chunk for v in point))
                        count = len(chunk) - 1
                    elif flags & 1:
                        await send(8, bytes(run[offset] + run[offset + 1]))
                        count = 1
                    else:
                        break
                    offset += count
                    segments += count
        else:
            await send(2, b'\x00\x20\x01Graph FW required')
        await send(4)

    async def run(self):
        try:
            info = await self.transport.command(0)
            if len(info) != 5 or info[:4] != bytes([128, 64, 16, 21]):
                raise RuntimeError('Unsupported OLED dimensions or text limits')
            graphics = None
            try:
                caps = await self.transport.command(7)
                if len(caps) != 5 or caps[0] != 1:
                    raise RuntimeError('Unsupported OLED graphics capabilities')
                graphics = caps[1], int.from_bytes(caps[2:4], 'little'), min(caps[4], 83)
            except DisplayError as exc:
                if exc.status != 3:
                    raise
            self.companion.logger.info('Companion OLED detected; displaying selected repeater battery.')
            while True:
                await self.draw(graphics)
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.companion.logger.warning('Companion OLED unavailable; radio continues normally: %s', str(exc) or type(exc).__name__)
            # No loop of unsupported commands on standard firmware. On errors,
            # the display lease expires; next reconnect probes again.
        finally:
            if self.acquired:
                try:
                    await asyncio.wait_for(self.transport.command(5), 3)
                except Exception:
                    pass
                self.acquired = False

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.transport:
            self.transport.detach()
