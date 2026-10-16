"""Configured reply dispatch plus existing position, scope and distance helpers."""
from meshcorestation.geometry import distance_km

from meshcorestation.storage.command_store import read as read_commands
from meshcorestation.commands.templates import fields, render
from meshcorestation.commands.context import collect

class Bot:
    def __init__(self, logger, companion, database):
        self.logger = logger
        self.companion = companion
        self.database = database
        self.position_update_running = False

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
        if command['action'] == 'position':
            template = template.replace('@{sender_name}', '@[{sender_name}]')
        try:
            needed = fields(template)
            values = await collect(self, needed, message_data, matched_rx, read_commands(self.database.db), outcome.message)
            values.update(outcome.values)
            return render(template, values)
        except ValueError:
            self.logger.warning('Configured reply could not be rendered for command %s', command['trigger'])
            return 'Reply configuration error. Please ask the MeshcoreStation owner to review this command.'

    def _get_value(self, data, *names, default=None):
        if not isinstance(data, dict):
            return default

        for name in names:
            if name in data:
                return data[name]

        return default

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
        return distance_km((lat1, lon1), (lat2, lon2))

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
