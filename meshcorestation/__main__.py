"""Application entry point: one PID, one database, one radio session."""
import asyncio
import fcntl
import logging
import signal
from meshcorestation.config import DATA_DIR, HOST, PORT
from meshcorestation.logging_setup import Logger
from meshcorestation.storage.database import Database
from meshcorestation.storage.voltage_store import initialize
from meshcorestation.runtime import Runtime
from meshcorestation.web_server import WebServer


async def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Refuse a second local instance before it can open the radio or web listener.
    with (DATA_DIR / 'meshcorestation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('Another MeshcoreStation instance is already running') from None
        logger = Logger()
        database = Database(logger)
        web = task = None
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        try:
            initialize(database.db)
            web = WebServer()
            web.start()
            logging.info('MeshcoreStation serving on http://%s:%s', HOST, PORT)
            task = asyncio.create_task(Runtime(logger, database).run(), name='meshcorestation-radio')
            while not stop.is_set():
                if task.done():
                    await task
                    raise RuntimeError('Radio runtime exited unexpectedly')
                if not web.thread.is_alive():
                    raise RuntimeError('HTTP server exited unexpectedly')
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        finally:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if web is not None:
                await asyncio.to_thread(web.close)
            database.close()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(run())


if __name__ == '__main__':
    main()
