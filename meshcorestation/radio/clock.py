"""Initialize the companion RTC before timestamped mesh requests are enabled."""
import asyncio
import time
from meshcore import EventType

TOLERANCE = 5


def host_time():
    now = int(time.time())
    if not 1704067200 <= now <= 0xFFFFFFFF:
        raise RuntimeError('Pi clock is invalid; check system time/NTP before connecting the companion.')
    return now


async def read_clock(commands):
    reply = await asyncio.wait_for(commands.get_time(), timeout=10)
    if reply is None or reply.type != EventType.CURRENT_TIME or not isinstance(reply.payload, dict):
        raise RuntimeError('Could not read companion clock.')
    value = reply.payload.get('time')
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise RuntimeError('Companion returned an invalid clock value.')
    return value


async def synchronize_clock(commands, logger):
    # Firmware rejects backward clock changes. Never push a future timestamp
    # merely to bypass replay protection; the Pi must have the correct time.
    host_time()
    before = await read_clock(commands)
    now = host_time()
    if before > now + TOLERANCE:
        raise RuntimeError('Companion clock is ahead of the Pi; check Pi time/NTP. Clock was not moved backwards.')
    if before >= now:
        logger.info('Companion clock verified against Pi time.')
        return
    result = await asyncio.wait_for(commands.set_time(now), timeout=10)
    if result is None or result.type != EventType.OK:
        raise RuntimeError('Companion clock synchronization was rejected.')
    after = await read_clock(commands)
    if abs(after - host_time()) > TOLERANCE:
        raise RuntimeError('Companion clock synchronization could not be verified.')
    logger.info('Companion clock synchronized with Pi (previous lag: %s seconds).', now - before)
