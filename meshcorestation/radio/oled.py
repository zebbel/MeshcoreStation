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
    def __init__(self, companion, on_button=None):
        self.companion = companion
        self.on_button = on_button
        self.last_sequence = None
        self.original = companion.mc._reader
        self.pending = None
        self.request_id = 0
        companion.mc.connection_manager.set_reader(self)

    async def handle_rx(self, data):
        data = bytes(data)
        if data.startswith(MAGIC):
            # Unsolicited gestures have no status byte and must never satisfy
            # an outstanding display request. Never draw inside the reader.
            if len(data) >= 8 and data[7] == 0x80:
                if len(data) == 16 and data[6] == 0 and data[8] == 0 and data[9] in (1, 2, 3, 4):
                    sequence = int.from_bytes(data[10:12], 'little')
                    delta = None if self.last_sequence is None else (sequence - self.last_sequence) & 0xffff
                    if delta is None or 0 < delta < 0x8000:
                        self.last_sequence = sequence
                        if self.on_button:
                            self.on_button(data[9])
                return
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


def command_scene(db):
    rows = db.execute("""SELECT recv_time,sender,message FROM logger
        ORDER BY recv_time DESC,id DESC LIMIT 3""").fetchall()
    texts = [(0, 0, 'Last commands     2/2')]
    if not rows:
        texts.append((0, 24, 'No commands yet'))
    for index, row in enumerate(rows):
        stamp = time.strftime('%H:%M', time.localtime(row['recv_time'])) if row['recv_time'] else '--:--'
        texts.append((0, 8 + index * 16, ascii_text(f"{stamp} {row['sender'] or 'Unknown'}")))
        texts.append((0, 16 + index * 16, ascii_text(row['message'] or '-')))
    texts.append((0, 56, 'Short press: battery'))
    return texts, []


class OledDisplay:
    def __init__(self, companion):
        self.companion = companion
        self.transport = None
        self.task = None
        self.acquired = False
        self.page = 0
        self.page_count = 2
        self.buttons = False
        self.compatible = False
        self.redraw = asyncio.Event()

    def on_button(self, gesture):
        if self.buttons and gesture == 1:
            self.page = (self.page + 1) % self.page_count
            self.redraw.set()

    def start(self):
        # Board identity comes from the normal device query, before any private
        # protocol traffic. TFT and unknown models must not be probed.
        if getattr(self.companion, 'device_info', {}).get('model') not in ('Heltec V4 OLED', 'Heltec V4.3 OLED'):
            return
        if os.getenv('MESHCORESTATION_OLED', '1').lower() not in ('0', 'false', 'off'):
            self.transport = DisplayTransport(self.companion, self.on_button)
            self.task = asyncio.create_task(self.run(), name='companion-oled')

    async def draw(self, graphics):
        db = self.companion.database.db
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='oled_pages'").fetchone():
            from meshcorestation.storage.oled_store import active
            from meshcorestation.radio.oled_scene import render
            pages = active(db, time.time())
            self.page_count = len(pages)
            self.page %= self.page_count
            drawing = render(db, pages[self.page], time.time())
            send = self.transport.command
            await send(1, struct.pack('<H', 60))
            self.acquired = True
            if self.buttons:
                await send(10, b'\x01')
            for x,y,size,text in drawing['texts']:
                await send(2, bytes([x,y,size]) + text.encode('ascii'))
            if graphics:
                flags,capacity,max_points = graphics
                for line in drawing['lines'][:capacity]:
                    if flags & 1:
                        await send(8, bytes(line))
                    elif flags & 2 and max_points >= 2:
                        await send(9, bytes([2,*line]))
            await send(4)
            return
        page = self.page
        texts, runs = (command_scene(self.companion.database.db) if page else
                       scene(self.companion.database.db, time.time()))
        send = self.transport.command
        # BEGIN clears pending content and renews the lease, including after an
        # expired lease. Never retry append operations after an uncertain reply.
        await send(1, struct.pack('<H', 60))
        self.acquired = True
        if self.buttons:
            # Idempotent: preserves queued gestures on redraw, also restores
            # subscription if BEGIN reacquired an expired lease.
            await send(10, b'\x01')
        for x, y, text in texts:
            if not page and not graphics and y == 32:
                continue
            await send(2, bytes([x, y, 1]) + text.encode('ascii'))
        if graphics and not page:
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
        elif not page:
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
            self.compatible = True  # Matching private MCOD INFO confirms this extension.
            self.buttons = bool(graphics and graphics[0] & 4)
            self.companion.logger.info('Companion OLED detected; battery screen%s.',
                                       ' and short-press command page' if self.buttons else '')
            while True:
                self.redraw.clear()
                await self.draw(graphics)
                try:
                    await asyncio.wait_for(self.redraw.wait(), 10)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.companion.logger.warning('Companion OLED unavailable; radio continues normally: %s', str(exc) or type(exc).__name__)
            # No loop of unsupported commands on standard firmware. On errors,
            # the display lease expires; next reconnect probes again.
        finally:
            self.compatible = False
            self.buttons = False
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
