"""Import saved repeaters and refresh them after known-contact advertisements."""
import asyncio
import re
import time
from collections import Counter
from types import SimpleNamespace
from meshcore import EventType


class RepeaterSync:
    def __init__(self, companion):
        self.companion = companion
        self.pending = asyncio.Event()
        self.adverts = Counter()
        self.task = None
        self.subscriptions = []

    def import_contacts(self, event):
        # Contact snapshots are not received advertisements: do not inflate counts.
        if not isinstance(event.payload, dict):
            return
        for contact in event.payload.values():
            if not isinstance(contact, dict):
                continue
            try:
                self.companion.database.add_new_repeater(SimpleNamespace(payload=contact), observed=False)
            except (ValueError, TypeError) as exc:
                self.companion.logger.warning('Invalid saved repeater contact: %s', exc)

    def advertisement(self, event):
        key = (event.payload or {}).get('public_key')
        if isinstance(key, str) and re.fullmatch('[0-9a-fA-F]{64}', key):
            self.adverts[key.lower()] += 1
            self.pending.set()

    def start(self):
        # Callbacks only record work; radio commands run outside the event dispatcher.
        self.subscriptions = [self.companion.mc.subscribe(EventType.CONTACTS, self.import_contacts),
                              self.companion.mc.subscribe(EventType.ADVERTISEMENT, self.advertisement)]
        self.pending.set()
        self.task = asyncio.create_task(self.run(), name='repeater-sync')

    async def refresh(self):
        async with self.companion.control_lock:
            result = await self.companion.mc.commands.get_contacts(lastmod=0)
            if result is None or result.type != EventType.CONTACTS or not isinstance(result.payload, dict):
                raise RuntimeError('Could not read saved repeater contacts')
            self.import_contacts(result)
            # Apply notifications after import so previously missing rows count too.
            db = self.companion.database.db
            with db:
                for key, count in self.adverts.items():
                    db.execute('UPDATE repeaters SET last_seen=?,advert_count=advert_count+? WHERE public_key=?', (int(time.time()), count, key))
            self.adverts.clear()

    async def run(self):
        while True:
            await self.pending.wait()
            self.pending.clear()
            # Coalesce bursts of advertisements into one local serial contact read.
            await asyncio.sleep(1)
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.companion.logger.warning('Repeater synchronization: %s', exc)
                await asyncio.sleep(10)
                self.pending.set()

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        for subscription in self.subscriptions:
            subscription.unsubscribe()
        self.subscriptions.clear()
