"""Serial connection, message routing, packet matching, and scoped replies."""
import time
from collections import deque
import asyncio
import hashlib
import hmac
from meshcore import MeshCore, EventType

from meshcorestation.radio.clock import synchronize_clock
from meshcorestation.radio.bot import Bot
from meshcorestation.commands.templates import split_reply
from meshcorestation.radio.repeater_sync import RepeaterSync

BAUDRATE = 115200
MAX_RECENT_RX_LOGS = 20
RX_MATCH_WINDOW_SECONDS = 15

class Companion:
    def __init__(self, logger, database):
        self.logger = logger
        self.mc = None
        self.repeater_sync = None
        self.database = database
        settings = database.get_bot_settings()
        self.serial_port = settings["serial_port"]
        self.channel_name = settings["channel_name"]
        self.bot = Bot(logger, self, database)
        self.channel_idx = None
        self.channel_hash = None
        self.recent_rx_logs = deque(maxlen=MAX_RECENT_RX_LOGS)
        self.reply_lock = asyncio.Lock()
        self.control_lock = asyncio.Lock()

################################################
# CONNECTION FUNCTIONS
################################################

    async def connect(self):
        self.logger.info(f"Connecting to {self.serial_port}...")
        self.mc = await MeshCore.create_serial(self.serial_port, BAUDRATE, debug=False)

        if self.mc is None:
            self.logger.error("Could not connect to MeshCore companion.")
            return False

        command_lock = asyncio.Lock()
        original_send = self.mc.commands.send

        async def serialized_send(*args, **kwargs):
            async with command_lock:
                return await original_send(*args, **kwargs)

        self.mc.commands.send = serialized_send

        # Complete RTC initialization before subscriptions, monitoring or controls.
        await synchronize_clock(self.mc.commands, self.logger)

        self.logger.info("MeshCore companion connected.")
        self.mc.set_decrypt_channel_logs(True)

        # A fresh install has no selected channel; never select an empty radio slot.
        self.channel_idx, channel = await self._find_channel_by_name(self.channel_name) if self.channel_name.strip() else (None, None)
        self.channel_hash = (channel or {}).get("channel_hash")

        if self.channel_idx is None:
            self.logger.error(f"Channel '{self.channel_name}' was not found.")
            self.logger.warning("Select a bot channel in the dashboard; replies are disabled until then.")

        try:
            info = await self.get_self_info()

            if not isinstance(info, dict):
                raise ValueError("No companion self information")

            latitude, longitude = float(info.get("adv_lat")), float(info.get("adv_lon"))

            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude, longitude) == (0, 0):
                raise ValueError("Missing or invalid bot coordinates")

            self.database.save_companion_position(info.get("public_key"), info.get("name") or info.get("adv_name") or "MeshCore bot", latitude, longitude, None, is_bot=True)
            self.logger.info("Bot position saved: latitude=%s, longitude=%s", latitude, longitude)

        except Exception as exc:
            self.logger.warning("Could not save bot position at startup: %s", exc)

        return True

    async def disconnect(self):
        if self.repeater_sync is not None:
            await self.repeater_sync.close()
            self.repeater_sync = None
        if self.mc is not None:
            await self.mc.disconnect()
            self.logger.info("Serial connection closed.")

    async def subscribe(self):
        self.mc.subscribe(EventType.NEW_CONTACT, self.database.add_new_repeater)
        self.mc.subscribe(EventType.RX_LOG_DATA, self._handle_rx_log)
        self.mc.subscribe(EventType.CHANNEL_MSG_RECV, self._handle_channel_message)
        self.repeater_sync = RepeaterSync(self)
        self.repeater_sync.start()
        await self.mc.start_auto_message_fetching()

################################################
# SEND FUNCTIONS
################################################

    async def send_channel_message(self, channel, message, matched_rx):
        try:
            scope_name, scope_key = self._get_reply_scope(matched_rx)
        except Exception as exc:
            self.logger.warning("Reply skipped: %s %s", type(exc).__name__, exc)
            return False

        if scope_name is None:
            scope_name = "unscoped (unknown request scope)"
            scope_key = None
            message = "scope not known"

        async with self.reply_lock:
            try:
                result = await self.mc.commands.set_flood_scope("*" if scope_key is None else scope_key)

                if result is None or result.type != EventType.OK:
                    self.logger.warning("Reply skipped: could not select scope %s", scope_name)
                    return False

                result = await self.mc.commands.send_chan_msg(channel, message)

                if result is None or result.type != EventType.OK:
                    self.logger.warning("Reply send failed: %s", getattr(result, "payload", None))
                    return False

                self.logger.info(f"Reply sent | scope: {scope_name}")
                return scope_name

            except Exception as exc:
                self.logger.warning("Scoped reply failed: %s %s", type(exc).__name__, exc)
                return False

            finally:
                try:
                    result = await self.mc.commands.set_flood_scope(None)

                    if result is None or result.type != EventType.OK:
                        self.logger.warning("WARNING: could not reset temporary reply scope")

                except Exception as exc:
                    self.logger.warning("WARNING: scope reset failed: %s %s", type(exc).__name__, exc)


    def _get_reply_scope(self, matched_rx):
            if matched_rx is None:
                raise ValueError("No matching RX packet")
    
            route_type = matched_rx.get("route_type")
    
            if route_type in (1, 2):
                return "unscoped", None
    
            if route_type not in (0, 3):
                raise ValueError("Missing or invalid RX route type")
    
            codes = bytes.fromhex(matched_rx["transport_code"])
            payload = matched_rx["pkt_payload"]
    
            if len(codes) != 4 or not isinstance(payload, bytes) or not payload or matched_rx.get("payload_type") != 5:
                raise ValueError("Invalid scope data in RX packet")
    
            received_code = int.from_bytes(codes[:2], "little")
            matches = {}
    
            for scope in self.database.get_scopes():
                key = bytes.fromhex(scope["scope_key"])
    
                if len(key) != 16 or key == bytes(16):
                    raise ValueError(f"Invalid stored scope key for {scope['name']}")
    
                digest = hmac.new(key, bytes([5]) + payload, hashlib.sha256).digest()
                code = int.from_bytes(digest[:2], "little")
                code = 1 if code == 0 else 65534 if code == 65535 else code
    
                if code == received_code:
                    matches[key] = scope["name"]
    
            if not matches:
                return None, None
    
            if len(matches) != 1:
                raise ValueError(f"Expected one matching scope key, found {len(matches)}")
    
            key, name = next(iter(matches.items()))
            return name, key

################################################
# STATUS FUNCTIONS
################################################

    async def get_status(self):
        core_result = await self.mc.commands.get_stats_core()
        radio_result = await self.mc.commands.get_stats_radio()
        packets_result = await self.mc.commands.get_stats_packets()

        core = core_result.payload or {} if core_result.type != EventType.ERROR else {}
        radio = radio_result.payload or {} if radio_result.type != EventType.ERROR else {}
        packets = packets_result.payload or {} if packets_result.type != EventType.ERROR else {}

        return core, radio, packets

    async def get_self_info(self):
        result = await self.mc.commands.send_appstart()

        if result.type != EventType.SELF_INFO:
            self.logger.warning("Could not read companion information: %s", result.payload)
            return None

        return result.payload

################################################
# CHANNEL MESSAGE FUNCTIONS
################################################

    async def _handle_channel_message(self, event):
        async with self.control_lock:
            await self._process_channel_message(event)

    async def _process_channel_message(self, event):
        if self.channel_idx is None:
            return
        message_data = dict(event.payload or {})
        message_data["raw_text"] = str(message_data.get("text", "")).rstrip("\x00")
        message_data["name"], message_data["message"] = self._parse_channel_message(message_data["raw_text"])

        hops = self._get_message_hops(message_data)
        message_data["path"] = f"{hops} hops" if hops is not None else "? hops"
        
        if message_data.get("channel_idx") != self.channel_idx:
            return

        command = self.bot.match_command(message_data['message'])
        if command is not None:
            self.logger.info("%s | sender=%r | path=%r", command['trigger'], message_data['name'], message_data['path'])
            matched_rx = self._find_matching_rx(message_data)
            reply = await self.bot.handle_message(message_data, matched_rx, command)
            if not reply:
                return
            sent = []
            for part in split_reply(reply):
                if sent:
                    await asyncio.sleep(1)
                scope_name = await self.send_channel_message(self.channel_idx, part, matched_rx)
                if scope_name is False:
                    break
                if scope_name == 'unscoped (unknown request scope)':
                    sent = ['scope not known']
                    break
                sent.append(part)
            if sent:
                self.database.add_logger(message_data, matched_rx, scope_name if scope_name is not False else 'partial reply', ''.join(sent))

################################################
# RX LOG FUNCTIONS
################################################

    def _handle_rx_log(self, event):
        rx = event.payload or {}
        from meshcorestation.storage.passive_stats import collector
        collector.submit(rx)
        
        payload_type = rx.get("payload_type")
        payload_typename = str(rx.get("payload_typename", "")).upper()

        if payload_type != 5 and payload_typename != "GRP_TXT":
            return

        rx_channel_hash = self._get_rx_channel_hash(rx)

        if self.channel_hash is not None and rx_channel_hash is not None and rx_channel_hash != self.channel_hash:
            return

        try:
            path_len = int(rx.get("path_len", 0))
        except (TypeError, ValueError):
            path_len = 0

        entry = dict(rx)
        entry["seen_at"] = time.monotonic()
        entry["path_len"] = path_len
        entry["path_hash_size"] = rx.get("path_hash_size", 1)
        entry["channel_hash"] = rx_channel_hash
        entry["channel_name"] = rx.get("chan_name")

        self.recent_rx_logs.append(entry)
        self._remove_old_rx_logs()

    def _get_rx_channel_hash(self, rx):
        pkt_payload = rx.get("pkt_payload")

        if isinstance(pkt_payload, (bytes, bytearray)) and len(pkt_payload) > 0:
            return f"{pkt_payload[0]:02x}"

        if isinstance(pkt_payload, list) and len(pkt_payload) > 0:
            return f"{int(pkt_payload[0]) & 0xFF:02x}"

        return None

    def _remove_old_rx_logs(self):
        now = time.monotonic()

        while self.recent_rx_logs and now - self.recent_rx_logs[0]["seen_at"] > RX_MATCH_WINDOW_SECONDS:
            self.recent_rx_logs.popleft()

    def _find_matching_rx(self, msg):
        self._remove_old_rx_logs()
        hops = self._get_message_hops(msg)
        timestamp = msg.get("sender_timestamp")
        raw_text = msg.get("raw_text")
        mode = msg.get("path_hash_mode")
        matches = []

        if hops is None or timestamp is None or raw_text is None:
            return None

        for rx in self.recent_rx_logs:
            if rx.get("channel_name") != self.channel_name or rx.get("channel_hash") != self.channel_hash:
                continue

            if rx.get("message") != raw_text or rx.get("sender_timestamp") != timestamp:
                continue

            if rx.get("path_len") != hops:
                continue

            if mode is not None and mode >= 0 and rx.get("path_hash_size") != mode + 1:
                continue

            matches.append(rx)

        paths = {(rx.get("path_hash_size"), rx.get("path"), rx.get("route_type"), rx.get("transport_code"), rx.get("pkt_payload")) for rx in matches}
        return matches[-1] if len(paths) == 1 else None

################################################
# TELEMETRY FUNCTIONS
################################################

    async def get_sender_contact(self, contact_name):
        result = await self.mc.commands.get_contacts()

        if result.type != EventType.CONTACTS:
            self.logger.warning("Could not load contacts: %s", result.payload)
            return None

        wanted_name = contact_name.strip().casefold()
        matches = [contact for contact in (result.payload or {}).values() if contact.get("adv_name", "").strip().casefold() == wanted_name]

        if len(matches) != 1:
            self.logger.warning(f"Expected one contact named {contact_name!r}, found {len(matches)}")
            return None

        return matches[0]

    async def get_telemetry(self, contact_name, matched_rx=None):
        contact = await self.get_sender_contact(contact_name)
        if contact is None:
            return None
        scope_name, scope_key = self._get_reply_scope(matched_rx)
        if scope_name is None:
            self.logger.warning("Telemetry skipped: received command scope is unknown")
            return None
        # Share the reply lock so no other transmission changes our temporary scope.
        async with self.reply_lock:
            try:
                result = await self.mc.commands.set_flood_scope("*" if scope_key is None else scope_key)
                if result is None or result.type != EventType.OK:
                    self.logger.warning("Telemetry skipped: could not select scope %s", scope_name)
                    return None
                result = await self.mc.commands.reset_path(contact["public_key"])
                if result is None or result.type != EventType.OK:
                    self.logger.warning("Could not reset route for %r: %s", contact_name, getattr(result, "payload", None))
                    return None
                self.logger.info("Requesting telemetry from %r using flooding | scope: %s", contact_name, scope_name)
                telemetry = await self.mc.commands.req_telemetry_sync(contact, timeout=60)
                if telemetry is None:
                    self.logger.warning("No telemetry response from %r | scope: %s", contact_name, scope_name)
                    return None
                return {"contact": contact, "telemetry": telemetry}
            finally:
                # Clear the temporary override, restoring the configured default.
                try:
                    result = await self.mc.commands.set_flood_scope(None)
                    if result is None or result.type != EventType.OK:
                        self.logger.warning("WARNING: could not reset temporary telemetry scope")
                except Exception as exc:
                    self.logger.warning("WARNING: telemetry scope reset failed: %s %s", type(exc).__name__, exc)

################################################
# HELPER FUNCTIONS
################################################

    async def _find_channel_by_name(self, channel_name):
        wanted_name = channel_name.strip().casefold()

        info = await self.mc.commands.send_device_query()
        capacity = (info.payload or {}).get('max_channels') if info and info.type == EventType.DEVICE_INFO else None
        if type(capacity) is not int or not 1 <= capacity <= 255:
            raise RuntimeError('Could not read channel capacity')
        for idx in range(capacity):
            result = await self.mc.commands.get_channel(idx)

            if result.type == EventType.ERROR:
                continue

            channel = result.payload or {}
            name = str(channel.get("channel_name", "")).strip().rstrip("\x00")

            if name.casefold() == wanted_name:
                self.logger.info(f"Found channel '{name}' at index {idx}")
                return idx, channel

        return None, None

    def _parse_channel_message(self, text):
        text = text.strip()

        if ":" in text:
            sender, message = text.split(":", 1)
            return sender.strip(), message.strip()

        return "unknown", text

    def _get_message_hops(self, msg):
        path_len = msg.get("path_len")

        if path_len is None:
            return None

        try:
            path_len = int(path_len)
        except (TypeError, ValueError):
            return None

        if path_len == 255:
            return 0

        if path_len > 63:
            return path_len & 0x3F

        return path_len