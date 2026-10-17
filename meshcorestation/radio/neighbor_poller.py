"""Opt-in, rate-limited neighbor sampling on the companion's owning event loop."""
import asyncio
import time
from meshcorestation.storage import optimizer_store
from meshcorestation.radio.repeater_transport import RepeaterTransport, TIMEOUT


class NeighborPoller:
    def __init__(self, companion):
        self.companion=companion
        self.task=None

    def start(self):
        optimizer_store.initialize()
        # Downtime must not produce a burst of catch-up radio polls.
        now=time.time()
        with optimizer_store.connect() as db:
            db.execute("""UPDATE profiles SET next_poll=CASE polling
                           WHEN '12h' THEN ? WHEN '24h' THEN ? END
                          WHERE polling!='manual' AND next_poll<?""",
                       (now+43200,now+86400,now))
            db.commit()
        self.task=asyncio.create_task(self.run(),name='opt-in-neighbor-poller')

    async def run(self):
        # All mode changes are stored first; a scheduler tick never sends
        # anything unless an explicit 12h or 24h opt-in exists.
        while True:
            await asyncio.sleep(60)
            row=optimizer_store.due()
            if row is None:
                continue
            key=row['public_key']
            if not optimizer_store.claim_poll(key):
                continue
            # No queued attempts: failed reads are not retried before next interval.
            try:
                async with self.companion.control_lock:
                    transport=RepeaterTransport(self.companion)
                    contact=await transport.contact(key)
                    # A blank login uses existing companion ACL rights.
                    # Passwords are NEVER stored for scheduled polling.
                    await transport.login(contact,'')
                    data=await asyncio.wait_for(
                        self.companion.mc.commands.req_neighbours_sync(
                            contact,count=15,offset=0,timeout=TIMEOUT), TIMEOUT+10)
                    if not isinstance(data,dict):
                        raise ValueError('No neighbor response from repeater.')
                    optimizer_store.save_neighbors(key,data,'scheduled')
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                optimizer_store.poll_error(key,str(exc))
                self.companion.logger.warning('Scheduled neighbor read skipped: %s',type(exc).__name__)

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
            self.task=None
