"""Configured reply dispatch plus existing position, scope and distance helpers."""
import math
import sqlite3

from meshcorestation.storage.command_store import read as read_commands
from meshcorestation.commands.templates import fields, render
from meshcorestation.commands.context import collect

class Bot:
    def __init__(self, logger, companion, database):
        self.logger = logger
        self.companion = companion
        self.database = database
        self.position_update_running = False

################################################
# MESSAGE FUNCTIONS
################################################

    def match_command(self, text):
        parts = text.strip().split(maxsplit=1)
        if not parts:
            return None
        return next((item for item in read_commands(self.database.db) if item['trigger'] == parts[0].casefold()), None)

    async def handle_message(self, message_data, matched_rx, command=None):
        command = command or self.match_command(message_data['message'])
        if command is None:
            return None
        from meshcorestation.commands.actions import execute
        outcome = await execute(self, command['action'], message_data, matched_rx)
        template = command['reply'] if outcome.ok else command.get('failure_reply', '@{sender_name} | {result}')
        try:
            needed = fields(template)
            values = await collect(self, needed, message_data, matched_rx, read_commands(self.database.db), outcome.message)
            values.update(outcome.values)
            return render(template, values)
        except ValueError:
            self.logger.warning('Configured reply could not be rendered for command %s', command['trigger'])
            return 'Reply configuration error. Please ask the MeshcoreStation owner to review this command.'

################################################
# HELP FUNCTIONS
################################################

    def _get_help_text(self):
        from meshcorestation.commands.templates import command_list
        return command_list(read_commands(self.database.db))

################################################
# STATUS FUNCTIONS
################################################

    async def _get_status_text(self):
        core, radio, packets = await self.companion.get_status()

        battery_mv = self._get_value(core, "battery_mv", "battery")
        uptime = self._get_value(core, "uptime_secs", "uptime")
        queue_len = self._get_value(core, "queue_len", "queue")
        errors = self._get_value(core, "errors", "error_flags")
    
        noise_floor = self._get_value(radio, "noise_floor")
        last_rssi = self._get_value(radio, "last_rssi", "RSSI")
        last_snr = self._get_value(radio, "last_snr", "SNR")
    
        packets_rx = self._get_value(packets, "packets_received", "packets_recv", "recv", "rx")
        packets_tx = self._get_value(packets, "packets_sent", "sent", "tx")
    
        repeater_count = self.database.get_repeater_count()
    
        parts = ["status"]
    
        if battery_mv is not None:
            parts.append(f"{battery_mv / 1000:.2f}V")
    
        if uptime is not None:
            parts.append(f"up {self._format_uptime(uptime)}")
    
        if noise_floor is not None:
            parts.append(f"NF {noise_floor}")
    
        if last_rssi is not None:
            parts.append(f"RSSI {last_rssi}")
    
        if last_snr is not None:
            parts.append(f"SNR {last_snr:+.1f}")
    
        if packets_rx is not None:
            parts.append(f"RX {packets_rx}")
    
        if packets_tx is not None:
            parts.append(f"TX {packets_tx}")
    
        if queue_len is not None:
            parts.append(f"Q {queue_len}")
    
        if errors not in (None, 0):
            parts.append(f"ERR {errors}")
    
        parts.append(f"repeaters {repeater_count}")
    
        return " | ".join(parts)

    def _get_value(self, data, *names, default=None):
        if not isinstance(data, dict):
            return default

        for name in names:
            if name in data:
                return data[name]

        return default

################################################
# PING FUNCTIONS
################################################

    async def _handle_ping(self, message_data, matched_rx):
        reply_parts = [f"@[{message_data['name']}]", "pong", message_data['path']]

        if matched_rx is not None:
            rx_path = self._format_rx_path(matched_rx)
            snr = matched_rx.get("snr")
            rssi = matched_rx.get("rssi")

            if rx_path and rx_path != message_data['path']:
                reply_parts.append(f"path {rx_path}")

            if snr is not None:
                reply_parts.append(f"SNR {snr:+.1f} dB")

            if rssi is not None:
                reply_parts.append(f"RSSI {rssi} dBm")

        reply_parts.append(await self._get_distance_text(message_data, matched_rx))
        reply = " | ".join(reply_parts)

        self.logger.info("Reply: %s", reply)
        return reply

################################################
# UPDATE COMPANION POSITION FUNCTIONS
################################################

    async def _update_position(self, contact_name):
        if self.position_update_running:
            return "Position update already running; try again shortly."

        self.position_update_running = True

        try:
            result = await self.companion.get_telemetry(contact_name)

            if result is None:
                return "Could not retrieve telemetry; saved position unchanged."

            contact = result["contact"]
            telemetry = result["telemetry"]
            gps = next((item.get("value") for item in telemetry if item.get("type") == "gps" and item.get("channel") == 1), None)

            if not isinstance(gps, dict):
                return "No GPS position in telemetry; saved position unchanged."

            latitude = float(gps["latitude"])
            longitude = float(gps["longitude"])
            altitude = gps.get("altitude")
            altitude = float(altitude) if altitude is not None else None

            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return "Invalid GPS coordinates; saved position unchanged."

            if altitude is not None and not math.isfinite(altitude):
                return "Invalid GPS altitude; saved position unchanged."

            self.database.save_companion_position(contact["public_key"], contact["adv_name"], latitude, longitude, altitude)

            self.logger.info(f"Position saved for {contact_name}: lat={latitude}, lon={longitude}, altitude={altitude}")
            return "Position updated and saved."

        except Exception as exc:
            self.logger.warning("Position update error: %s %s", type(exc).__name__, exc)
            return "Position update failed; check the bot log."

        finally:
            self.position_update_running = False

################################################
# ADD SCOPE FUNCTIONS
################################################

    def _add_scope(self, message):
        parts = message.strip().split(maxsplit=2)

        if len(parts) != 3 or parts[1].casefold() != "add":
            return "Usage: scope add <name>"

        try:
            name, added = self.database.add_scope(parts[2])
        except ValueError as exc:
            return str(exc)
        except sqlite3.Error as exc:
            self.logger.warning("Scope database error: %s", exc)
            return "Could not save scope; check the bot log."

        return f"Scope {name} added." if added else f"Scope {name} already exists."

################################################
# DISTANCE FUNCTIONS
################################################

    async def _get_distance_text(self, message_data, matched_rx):
        try:
            positions = self.database.get_companion_positions_by_name(message_data["name"])

            if not positions:
                return "Distance unavailable: send position first"

            if len(positions) != 1:
                return "Distance unavailable: duplicate saved names"

            own_info = await self.companion.get_self_info()

            if not own_info:
                return "Distance unavailable: cannot read bot position"

            start = self._valid_position(positions[0]["latitude"], positions[0]["longitude"])
            end = self._valid_position(own_info.get("adv_lat"), own_info.get("adv_lon"))

            if start is None or end is None:
                return "Distance unavailable: missing or invalid coordinates"

            direct = self._distance_km(*start, *end)
            route = self._get_route_distance_text(start, end, message_data, matched_rx)
            return f"Direct {direct:.2f} km | {route}"

        except (KeyError, TypeError, ValueError) as exc:
            self.logger.warning("Distance calculation error: %s %s", type(exc).__name__, exc)
            return "Distance unavailable: invalid data"

    def _get_route_distance_text(self, start, end, message_data, matched_rx):
        hops = self.companion._get_message_hops(message_data)

        if hops == 0:
            return f"Route {self._distance_km(*start, *end):.2f} km"

        if matched_rx is None:
            return "Route unavailable: no matching RX"

        try:
            size = int(matched_rx["path_hash_size"])
            count = int(matched_rx["path_len"])
            raw_path = matched_rx["path"]
            path = bytes.fromhex(raw_path) if isinstance(raw_path, str) else bytes(raw_path)

            if size not in (1, 2, 3) or count != hops or not (1 <= count <= 63) or len(path) != count * size:
                raise ValueError("Invalid repeater path")

        except (KeyError, TypeError, ValueError):
            return "Route unavailable: invalid path"

        identifiers = [path[i:i + size].hex() for i in range(0, len(path), size)]
        layers = []
        unresolved = 0

        for identifier in identifiers:
            rows = self.database.get_repeaters_by_prefix(identifier)
            candidates = [(row["public_key"], self._valid_position(row["latitude"], row["longitude"])) for row in rows]

            if not candidates or any(position is None for key, position in candidates):
                unresolved += 1
                continue

            layers.append(candidates)

        if unresolved:
            # With gaps, use only uniquely identified repeaters as fixed waypoints.
            unresolved += sum(len(layer) > 1 for layer in layers)
            layers = [layer for layer in layers if len(layer) == 1]

        ambiguous = any(len(layer) > 1 for layer in layers)
        states = [(start, [(0.0, ())])]

        # Keep the two shortest alternatives ending at each candidate.
        for layer in layers + [[("bot", end)]]:
            next_states = []

            for key, position in layer:
                options = sorted((cost + self._distance_km(*previous, *position), keys + (key,)) for previous, alternatives in states for cost, keys in alternatives)[:2]
                next_states.append((position, options))

            states = next_states

        alternatives = states[0][1]
        best_distance, keys = alternatives[0]

        if ambiguous:
            second_distance = alternatives[1][0]

            # Geographic heuristic: the alternative must be at least 20% and 5 km longer.
            if second_distance - best_distance < max(5.0, best_distance * 0.20):
                return "Route ambiguous"

            self.logger.info("Geographically selected repeater keys: %s", keys[:-1])
            return f"Route ~{best_distance:.2f} km (estimated IDs)"

        if unresolved:
            return f"Route >={best_distance:.2f} km ({unresolved} unresolved)"

        return f"Route {best_distance:.2f} km"

    def _valid_position(self, latitude, longitude):
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (TypeError, ValueError):
            return None

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return None

        return None if (latitude, longitude) == (0, 0) else (latitude, longitude)

    def _distance_km(self, lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1
        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        return 6371.0088 * 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))

################################################
# HELPER FUNCTIONS
################################################

    def _format_rx_path(self, rx):
        hops = rx.get("path_len")
        path = rx.get("path", "")
        hash_size = rx.get("path_hash_size", 1)

        if hops is None:
            return None

        try:
            hops = int(hops)
            hash_size = int(hash_size)
        except (TypeError, ValueError):
            return None

        if hops == 0:
            return "0 hops"

        if isinstance(path, bytes):
            path = path.hex()

        path = str(path).lower().replace(" ", "")

        if not path:
            return f"{hops} hops"

        chars_per_hash = hash_size * 2
        nodes = [path[i:i + chars_per_hash] for i in range(0, len(path), chars_per_hash)]

        return f"{hops} hops [{':'.join(nodes)}]"

    def _format_uptime(self, seconds):
        if seconds is None:
            return "?"

        seconds = int(seconds)
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, _ = divmod(seconds, 60)

        if days:
            return f"{days}d{hours}h"

        if hours:
            return f"{hours}h{minutes}m"

        return f"{minutes}m"
