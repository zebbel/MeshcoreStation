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
        self.connected = False
        self.dropped = self.invalid = 0
        self.error = ''
        self.errors = {}
        self.last_write = None

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

    async def close(self):
        self.connected = False
        self.stopping = True
        if self.task is not None:
            await self.task
