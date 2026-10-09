"""Thread-safe handoff from HTTP workers to the radio's asyncio event loop."""
import asyncio
import concurrent.futures


class RuntimeBridge:
    def __init__(self):
        self.runtime = None
        self.loop = None
        self.status = ('Starting', 'MeshcoreStation is starting', 'unknown')

    def attach(self, runtime):
        self.runtime = runtime
        self.loop = asyncio.get_running_loop()

    def request(self, payload, timeout=180):
        # All radio and bot database access stays on the owning event-loop thread.
        if self.runtime is None or self.loop is None or self.loop.is_closed():
            raise OSError('MeshcoreStation runtime unavailable')
        future = asyncio.run_coroutine_threadsafe(self.runtime.dispatch(payload), self.loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.CancelledError:
            raise OSError('Companion is reconnecting; refresh before retrying') from None
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise OSError('Companion request timed out; refresh before retrying') from None

    def reconnect(self):
        if self.runtime is None or self.loop is None or self.loop.is_closed():
            raise RuntimeError('MeshcoreStation runtime unavailable')
        self.loop.call_soon_threadsafe(self.runtime.reconnect_requested.set)

    def detach(self):
        self.runtime = self.loop = None
        self.status = ('Stopped', 'MeshcoreStation stopped', 'stopped')


bridge = RuntimeBridge()
