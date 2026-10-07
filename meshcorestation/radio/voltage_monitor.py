"""One background worker owns scheduled telemetry and report attempts."""
import asyncio
import hashlib
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from meshcore import EventType
from meshcorestation.radio.channels_control import channel_type
from meshcorestation.radio.contacts_control import new_contact
from meshcorestation.storage.voltage_store import initialize, config, latest, extract_voltage, due_slots


class VoltageMonitor:
    def __init__(self, companion):
        self.companion = companion
        self.db = companion.database.db
        initialize(self.db)
        self.task = None

    def heartbeat(self, state):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO voltage_worker VALUES (1,?,?)', (time.time(), state))

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.heartbeat('stopped')

    async def run(self):
        while True:
            try:
                self.heartbeat('waiting')
                async with self.companion.control_lock:
                    await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.companion.logger.warning('Voltage monitoring: %s', exc)
                self.heartbeat('error: ' + str(exc)[:200])
            await asyncio.sleep(10)

    async def sample(self, cfg):
        """Caller holds control_lock; request uses guest telemetry, never a password."""
        key = cfg['public_key']
        row = self.db.execute('SELECT name,latitude,longitude FROM repeaters WHERE lower(public_key)=?', (key,)).fetchone()
        name = row['name'] if row and row['name'] else key[:12]
        voltage, error = None, None
        self.heartbeat('reading telemetry')
        try:
            result = await self.companion.mc.commands.get_contacts()
            if result is None or result.type != EventType.CONTACTS or not isinstance(result.payload, dict):
                raise ValueError('Could not read companion contacts.')
            contacts = [v for v in result.payload.values() if isinstance(v, dict) and str(v.get('public_key', '')).lower() == key]
            if not contacts:
                # Monitoring a known repeater authorizes saving its contact if absent.
                safe_name = ''.join(ch for ch in name if ord(ch) >= 32 and ord(ch) != 127)
                safe_name = safe_name.encode('utf-8')[:31].decode('utf-8', errors='ignore').strip() or key[:12]
                value = {'public_key': key, 'name': safe_name, 'type': 2}
                if row and row['latitude'] is not None and row['longitude'] is not None:
                    value.update(latitude=row['latitude'], longitude=row['longitude'])
                contact = new_contact(value)
                added = await self.companion.mc.commands.add_contact(contact)
                if added is None or added.type != EventType.OK:
                    raise ValueError('Could not save repeater in companion contacts; check free contact space.')
                readback = await self.companion.mc.commands.get_contacts()
                if readback is None or readback.type != EventType.CONTACTS or not isinstance(readback.payload, dict):
                    raise ValueError('New repeater contact could not be verified.')
                contacts = [v for v in readback.payload.values() if isinstance(v, dict) and str(v.get('public_key', '')).lower() == key]
            if len(contacts) != 1 or contacts[0].get('type') != 2:
                raise ValueError('Selected public key is not one unambiguous Repeater contact.')
            # Password-free access still requires the guest login exchange so the
            # repeater knows this companion and its shared secret. Never try an
            # admin/default password or change the repeater's permissions.
            try:
                login = await asyncio.wait_for(self.companion.mc.commands.send_login_sync(contacts[0], "", timeout=60), timeout=70)
            except asyncio.TimeoutError:
                raise ValueError('Guest login timed out. Check repeater reachability and blank-password guest access.') from None
            if login is None or login.type != EventType.LOGIN_SUCCESS:
                raise ValueError('No successful guest login reply. Check repeater reachability and blank-password guest access.')
            prefix = (login.payload or {}).get('pubkey_prefix') if isinstance(login.payload, dict) else None
            if not isinstance(prefix, str) or prefix.lower() != key[:12]:
                raise ValueError('Guest login reply could not be matched to the selected repeater.')
            # Refresh the heartbeat between the two radio exchanges. Keep the
            # saved route; no repeated forced flooding or route resets.
            self.heartbeat('reading telemetry')
            try:
                telemetry = await asyncio.wait_for(self.companion.mc.commands.req_telemetry_sync(contacts[0], timeout=60), timeout=70)
            except asyncio.TimeoutError:
                raise ValueError('Guest login succeeded, but telemetry timed out. Check the radio path and guest telemetry support.') from None
            if telemetry is None:
                raise ValueError('Guest login succeeded, but no telemetry response arrived. Check the radio path and guest telemetry support.')
            voltage = extract_voltage(telemetry, cfg['voltage_channel'])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = (str(exc) or type(exc).__name__)[:300]
            self.companion.logger.warning('Voltage read for %s failed: %s', key[:12], error)
        stamp = time.time()
        with self.db:
            self.db.execute('''INSERT INTO voltage_samples
                (public_key,name,sampled_at,voltage,error,voltage_channel,interval_seconds)
                VALUES (?,?,?,?,?,?,?)''', (key, name, stamp, voltage, error,
                                          cfg['voltage_channel'], cfg['interval_minutes'] * 60))
        self.heartbeat('idle')
        return latest(self.db, cfg)

    async def tick(self):
        cfg = config(self.db)
        now = time.time()
        sample = latest(self.db, cfg)
        manual = cfg['request_seq'] > cfg['handled_seq']
        due = cfg['enabled'] and (not sample or now - sample['sampled_at'] >= cfg['interval_minutes'] * 60)
        if cfg['public_key'] and (manual or due):
            with self.db:
                self.db.execute('UPDATE voltage_config SET handled_seq=? WHERE id=1', (cfg['request_seq'],))
            sample = await self.sample(cfg)
        # Dashboard saves can happen while the radio request is in flight.
        if config(self.db)['revision'] != cfg['revision']:
            return
        for slot, due_at in due_slots(cfg, time.time()):
            with self.db:
                claimed = self.db.execute('''INSERT OR IGNORE INTO voltage_reports
                    (slot,public_key,due_at,attempted_at,status,detail) VALUES (?,?,?,?,?,?)''',
                    (slot, cfg['public_key'], due_at, time.time(), 'unconfirmed',
                     'Attempt reserved; interrupted attempts are not retransmitted automatically.')).rowcount
            if not claimed:
                continue
            if not sample or time.time() - sample['sampled_at'] > 120:
                sample = await self.sample(cfg)
            await self.report(slot, cfg, sample)
        self.heartbeat('idle')

    async def report(self, slot, cfg, sample):
        state, detail, channel_name = 'failed', '', None
        try:
            if config(self.db)['revision'] != cfg['revision']:
                raise ValueError('Settings changed during reading; report skipped.')
            c = self.companion
            index = c.channel_idx
            if index is None:
                raise ValueError('No bot channel selected.')
            result = await c.mc.commands.get_channel(index)
            if result is None or result.type != EventType.CHANNEL_INFO:
                raise ValueError('Could not verify the current bot channel.')
            channel = result.payload or {}
            channel_name, secret = channel.get('channel_name'), channel.get('channel_secret')
            if (channel.get('channel_idx') != index or channel_name != c.channel_name
                    or not isinstance(secret, bytes) or len(secret) != 16 or secret == bytes(16)
                    or hashlib.sha256(secret).digest()[:1].hex() != c.channel_hash):
                raise ValueError('Bot channel changed on device; reselect it in Channels.')
            if channel_type(channel_name, secret) != 'private':
                raise ValueError('Reports require a private bot channel; public/hashtag channel selected.')
            stamp = datetime.fromtimestamp(sample['sampled_at'], ZoneInfo(cfg['timezone'])).strftime('%d.%m %H:%M')
            name = ''.join(ch for ch in sample['name'] if ord(ch) >= 32 and ord(ch) != 127)[:31]
            reading = f'{sample["voltage"]:.2f} V' if sample['voltage'] is not None else 'unavailable (no valid reading)'
            message = f'Battery {name}: {reading} | {stamp}'
            async with c.reply_lock:
                # Proactive reports use the companion's configured default scope.
                reset = await c.mc.commands.set_flood_scope(None)
                if reset is None or reset.type != EventType.OK:
                    raise ValueError('Could not restore the default transmit scope; report skipped.')
                if config(self.db)['revision'] != cfg['revision']:
                    raise ValueError('Settings changed; report skipped.')
                state, detail = 'unconfirmed', 'Send attempted; acknowledgement not confirmed. No automatic retry.'
                sent = await c.mc.commands.send_chan_msg(index, message)
                if sent is not None and sent.type == EventType.OK:
                    state, detail = 'queued', message + ' (Companion accepted; delivery is not confirmed.)'
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            detail = (str(exc) or type(exc).__name__)[:300]
        with self.db:
            self.db.execute('UPDATE voltage_reports SET status=?,detail=?,channel_name=? WHERE slot=?', (state, detail, channel_name, slot))
        self.companion.logger.info('Voltage report: %s %s', state, detail)
