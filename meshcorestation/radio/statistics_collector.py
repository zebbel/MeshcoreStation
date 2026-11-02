"""Bounded asynchronous RX_LOG_DATA handoff; all SQLite work runs off-loop."""
import asyncio
import time
from meshcorestation.storage import passive_stats


class Collector:
    def __init__(self, main_path, logger, capacity=2048, batch_size=128, interval=0.5):
        self.main_path, self.logger = main_path, logger
        self.queue = asyncio.Queue(maxsize=capacity)
        self.batch_size, self.interval = batch_size, interval
        self.task = None
        self.stopping = False
        self._connected = False
        self._coverage_start = None
        self._coverage_losses = (0,0)
        self._coverage_clock = None
        self._coverage_tick = 0
        self.dropped = self.invalid = 0
        self.error = ''
        self.errors = {}
        self.last_write = None

    @property
    def connected(self):
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = bool(value)
        self._coverage_start = None

    async def coverage(self):
        now,mono=time.time(),time.monotonic()
        if self.error.startswith('Coverage recording unavailable:'):
            if mono-self._coverage_tick<5:return
            self.error=''
        if self.errors and self.connected and mono-self._coverage_tick>=5:
            try:
                managed=await asyncio.to_thread(passive_stats.active_keys,self.main_path)
                self.errors={key:error for key,error in self.errors.items() if key in managed}
            except Exception as exc:
                self.error='Coverage recording unavailable: '+str(exc)
        losses=(self.dropped,self.invalid)
        clock_gap=self._coverage_clock and abs((now-self._coverage_clock[0])-(mono-self._coverage_clock[1]))>2
        self._coverage_clock=(now,mono)
        if not self.connected or self.error or self.errors or not self.queue.empty() or losses!=self._coverage_losses or clock_gap:
            self._coverage_start=None
        self._coverage_losses=losses
        if not self.connected or self.error or self.errors or not self.queue.empty():return
        if self._coverage_start is None:self._coverage_start=now
        if mono-self._coverage_tick<5:return
        self._coverage_tick=mono
        try:
            await asyncio.to_thread(passive_stats.record_coverage,self.main_path,self._coverage_start,now)
            self._coverage_start=now
        except Exception as exc:
            self._coverage_start=None
            self.error='Coverage recording unavailable: '+str(exc)
            self.logger.warning('%s',self.error)

    def start(self):
        if self.task is None or self.task.done():
            self.stopping = False
            self.task = asyncio.create_task(self.run(), name='repeater-statistics-collector')

    def submit(self, rx):
        if self.stopping or self.task is None or self.task.done(): return
        packet = passive_stats.normalize(rx)
        if packet is None:
            self.invalid += 1
            return
        try: self.queue.put_nowait(packet)
        except asyncio.QueueFull:
            self.dropped += 1

    def health(self, key=''):
        return dict(running=bool(self.task and not self.task.done()), connected=self.connected,
                    queued=self.queue.qsize(), dropped=self.dropped, invalid=self.invalid,
                    error=self.error, repeater_error=self.errors.get(key, ''), last_write=self.last_write)

    async def run(self):
        while not self.stopping or not self.queue.empty():
            batch = []
            try:
                batch.append(await asyncio.wait_for(self.queue.get(), timeout=self.interval))
            except asyncio.TimeoutError:
                # A storage error can be retried on later observations. Coverage
                # remains unknown while that error persists.
                await self.coverage()
                continue
            # Coalesce short bursts instead of opening one transaction per callback.
            if not self.stopping: await asyncio.sleep(self.interval)
            while len(batch) < self.batch_size:
                try: batch.append(self.queue.get_nowait())
                except asyncio.QueueEmpty: break
            try:
                saved, failed = await asyncio.to_thread(passive_stats.store_batch, self.main_path, batch)
                for key in saved: self.errors.pop(key, None)
                for key, detail in failed.items():
                    self.errors[key] = detail['error']
                    self.dropped += detail['dropped']
                if saved: self.last_write = time.time()
                self.error = ''
            except Exception as exc:
                self.dropped += len(batch)
                self.error = 'Statistics write failed: '+str(exc)
                self.logger.warning('%s', self.error)
            finally:
                for _ in batch: self.queue.task_done()
            await self.coverage()

    async def close(self):
        self.connected = False
        self.stopping = True
        if self.task is not None:
            await self.task
