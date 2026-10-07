"""Own the radio session, battery worker, and graceful reconnects in one process."""
import asyncio
from meshcorestation.bridge import bridge
from meshcorestation.radio.companion import Companion
from meshcorestation.radio.companion_control import CompanionControl
from meshcorestation.radio.voltage_monitor import VoltageMonitor


class Runtime:
    def __init__(self, logger, database):
        self.logger, self.database = logger, database
        self.companion = self.control = self.voltage = None
        self.reconnect_requested = asyncio.Event()
        self.requests = set()

    async def dispatch(self, payload):
        """Serialize control changes with bot replies and telemetry requests."""
        control, companion = self.control, self.companion
        if control is None or companion is None:
            return {'ok': False, 'error': 'Companion offline. Select a serial port and check its connection.'}
        task = asyncio.current_task()
        self.requests.add(task)
        try:
            async with companion.control_lock:
                if control is not self.control:
                    return {'ok': False, 'error': 'Companion reconnected; refresh before retrying.'}
                return await control.execute(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'note': 'Read settings again before retrying a change.'}
        finally:
            self.requests.discard(task)

    async def close_session(self):
        # Block new requests before canceling in-flight work and closing the radio.
        self.control = None
        for task in tuple(self.requests):
            task.cancel()
        await asyncio.gather(*tuple(self.requests), return_exceptions=True)
        if self.voltage is not None:
            await self.voltage.close()
            self.voltage = None
        if self.companion is not None:
            try:
                await asyncio.wait_for(self.companion.disconnect(), timeout=10)
            except Exception as exc:
                self.logger.warning('Closing companion: %s', exc)
            self.companion = None

    async def session(self):
        self.companion = Companion(self.logger, self.database)
        if not await self.companion.connect():
            raise ConnectionError('No response from companion')
        await self.companion.subscribe()
        self.control = CompanionControl(self.companion)
        self.voltage = VoltageMonitor(self.companion)
        self.voltage.start()
        self.logger.set_log_level()
        while True:
            connected = self.companion.mc.connection_manager.is_connected
            bridge.status = ('Running', 'MeshcoreStation companion connected', 'running') if connected else ('Reconnecting', 'Companion connection lost', 'unknown')
            await asyncio.sleep(1)

    async def run(self):
        bridge.attach(self)
        try:
            while True:
                self.reconnect_requested.clear()
                bridge.status = ('Connecting', 'Opening the selected serial port', 'unknown')
                session = asyncio.create_task(self.session(), name='radio-session')
                reconnect = asyncio.create_task(self.reconnect_requested.wait())
                try:
                    done, _ = await asyncio.wait({session, reconnect}, return_when=asyncio.FIRST_COMPLETED)
                    if session in done:
                        await session
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    bridge.status = ('Offline', 'Check serial port in Settings', 'stopped')
                    self.logger.warning('Companion offline: %s', exc)
                finally:
                    session.cancel()
                    reconnect.cancel()
                    await asyncio.gather(session, reconnect, return_exceptions=True)
                    await self.close_session()
                # Failed connection attempts never prevent access to web settings.
                if not self.reconnect_requested.is_set():
                    try:
                        await asyncio.wait_for(self.reconnect_requested.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        pass
        finally:
            bridge.detach()
