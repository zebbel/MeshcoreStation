"""Opt-in, forward-only clock checks using Companion ACL access, never passwords."""
import asyncio
import time
from meshcorestation.radio.clock import host_time, read_clock
from meshcorestation.radio.repeater_control import RepeaterControl
from meshcorestation.radio.repeater_transport import RepeaterTransport
from meshcorestation.storage import clock_sync as store

STARTUP_DELAY = 60
ATTEMPT_GAP = 30
CHECK_INTERVAL = 10
TOLERANCE = 5
TIMESTAMP_GAP = 1.1


async def synchronized_host_time():
    """Fail closed if systemd cannot confirm the host's NTP synchronization."""
    host_time()
    process = None
    try:
        process = await asyncio.create_subprocess_exec('timedatectl', 'show', '--property=NTPSynchronized', '--value',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        output, _ = await asyncio.wait_for(process.communicate(), 3)
        if process.returncode != 0 or output.strip() != b'yes':
            raise ValueError('Host clock is not confirmed synchronized by NTP; no clock-setting command sent.')
    except (OSError, asyncio.TimeoutError):
        raise ValueError('Host time synchronization status unavailable; no clock-setting command sent.') from None
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
    return host_time()


async def durable(call, *args):
    """Drain a DB mutation before cancellation so the persisted fence is settled."""
    task = asyncio.create_task(asyncio.to_thread(call, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class ClockSyncWorker:
    def __init__(self, runtime, path):
        self.runtime, self.path = runtime, path
        self.task = None
        self.inflight = None
        self.next_slot = 0

    def start(self):
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.run(), name='repeater-clock-sync')

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    def connected(self, companion):
        return bool(companion and self.runtime.companion is companion and self.runtime.control is not None
                    and companion.mc.connection_manager.is_connected)

    async def guard(self, companion, cfg):
        if not self.connected(companion) or not await asyncio.to_thread(store.still_enabled, self.path, cfg):
            raise asyncio.CancelledError('Clock synchronization disabled, changed, removed or disconnected.')

    async def attempt(self, cfg, companion):
        cfg = dict(cfg)
        wrote = False
        claimed = False
        offset = None
        latency = 0
        state, error, success = 'error', '', False
        try:
            # Hold the same lock used by manual management, telemetry and SNR monitoring.
            async with companion.control_lock:
                await self.guard(companion, cfg)
                cfg['attempt_started'] = time.time()
                def claim():
                    nonlocal claimed
                    claimed = store.claim(self.path, cfg, cfg['attempt_started'])
                    return claimed
                if not await durable(claim): return
                await synchronized_host_time()
                await self.guard(companion, cfg)
                transport = RepeaterTransport(companion)
                contact = await transport.contact(cfg['public_key'])
                await self.guard(companion, cfg)
                start, mono = time.time(), time.monotonic()
                login = await transport.login(contact, '')
                end = time.time()
                await self.guard(companion, cfg)
                self.check_elapsed(start, end, mono)
                if login.get('is_admin') is not True:
                    raise ValueError('Administrator authorization unavailable for the Companion ACL; no clock-setting command sent.')
                remote = RepeaterControl.clock_timestamp(login)
                if remote is None: raise ValueError('Fresh login response did not contain a valid repeater clock.')
                offset = remote - (start+end)/2
                latency = end-start
                if remote > end+TOLERANCE:
                    state = 'ahead'
                    raise ValueError('Repeater clock is ahead of the host; backward synchronization is prohibited.')
                if remote >= start-TOLERANCE:
                    if remote < end-TOLERANCE or remote > start+TOLERANCE:
                        state = 'latency_uncertain'
                        raise ValueError('Communication latency prevents a precise clock comparison; no clock-setting command sent.')
                    state, success = 'verified', True
                    return
                # clock sync uses the sender/Companion timestamp. Verify its RTC too.
                await synchronized_host_time()
                companion_time = await read_clock(companion.mc.commands)
                if abs(companion_time-host_time())>TOLERANCE:
                    raise ValueError('Companion clock differs from the host; reconnect and verify time before synchronizing repeaters.')
                await asyncio.sleep(TIMESTAMP_GAP)  # distinct firmware request timestamp after login
                await self.guard(companion, cfg)
                self.check_elapsed(start, time.time(), mono)
                def fence():
                    nonlocal wrote
                    # durable() drains this commit even when the coroutine is cancelled.
                    wrote = store.mark_write(self.path, cfg)
                    return wrote
                if not await durable(fence):
                    raise asyncio.CancelledError('Clock configuration changed before submission.')
                await self.guard(companion, cfg)
                write_start, write_mono = time.time(), time.monotonic()
                reply = await transport.cli(contact, 'clock sync')  # exactly one submission, never retried
                write_elapsed = time.time()-write_start
                self.check_elapsed(write_start, time.time(), write_mono)
                if not isinstance(reply, str) or not reply.lower().startswith('ok'):
                    raise ValueError('Repeater did not acknowledge clock synchronization.')
                await asyncio.sleep(TIMESTAMP_GAP)
                await self.guard(companion, cfg)
                start, mono = time.time(), time.monotonic()
                readback = await transport.login(contact, '')
                end = time.time()
                self.check_elapsed(start, end, mono)
                await self.guard(companion, cfg)
                remote = RepeaterControl.clock_timestamp(readback)
                if readback.get('is_admin') is not True or remote is None:
                    raise ValueError('Clock readback or administrator authorization unavailable.')
                offset = remote-(start+end)/2
                latency = write_elapsed+end-start
                if not start-TOLERANCE-write_elapsed <= remote <= end+TOLERANCE:
                    raise ValueError('Clock readback differs from host time beyond communication latency tolerance.')
                state, success = 'synchronized', True
        except asyncio.CancelledError:
            state = 'verification_required' if wrote else 'interrupted'
            error = 'Clock write outcome uncertain; manually verify the clock before resuming.' if wrote else 'Clock check interrupted; saved schedule preserved.'
            raise
        except Exception as exc:
            state = 'verification_required' if wrote else state
            error = 'Clock write outcome uncertain; manually verify before resuming. ' + (str(exc) or type(exc).__name__) if wrote else str(exc) or type(exc).__name__
            self.runtime.logger.warning('Repeater clock %s: %s', cfg['public_key'][:12], error)
        finally:
            if claimed:
                await durable(store.finish, self.path, cfg, state, error, offset, success, wrote and success, latency)

    @staticmethod
    def check_elapsed(start, end, mono):
        if abs((end-start)-(time.monotonic()-mono)) > 2:
            raise ValueError('Host clock changed during synchronization; result cannot be verified.')

    async def tick(self):
        companion = self.runtime.companion
        if not self.connected(companion) or time.monotonic()<self.next_slot: return
        pending = await asyncio.to_thread(store.due, self.path, time.time())
        if not pending: return
        cfg = pending[0]
        self.inflight = asyncio.create_task(self.attempt(cfg, companion))
        try:
            # Revocation must also interrupt queued lock waiters and in-flight reads.
            deadline = time.monotonic()+180
            while not self.inflight.done():
                await asyncio.wait({self.inflight}, timeout=.25)
                if time.monotonic()>deadline: raise TimeoutError('Clock operation exceeded its bounded time budget.')
                await self.guard(companion, cfg)
            await self.inflight
        except asyncio.CancelledError:
            # A per-repeater revocation must not terminate the entire scheduler.
            if asyncio.current_task().cancelling(): raise
        finally:
            self.inflight.cancel()
            await asyncio.gather(self.inflight, return_exceptions=True)
            self.inflight = None
            self.next_slot = time.monotonic()+ATTEMPT_GAP

    async def run(self):
        recovered = False
        self.next_slot = time.monotonic()+STARTUP_DELAY
        try:
            while True:
                try:
                    if not recovered:
                        await durable(store.recover, self.path)
                        recovered = True
                    await self.tick()
                except asyncio.CancelledError: raise
                except Exception as exc:
                    self.runtime.logger.warning('Clock scheduler: %s', str(exc) or type(exc).__name__)
                await asyncio.sleep(CHECK_INTERVAL)
        finally:
            if self.inflight:
                self.inflight.cancel()
                await asyncio.gather(self.inflight, return_exceptions=True)
                self.inflight = None
