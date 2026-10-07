"""Map payloads; historical sender snapshots and current repeater/bot positions."""
import math
import sqlite3
from contextlib import closing
from meshcorestation.web import data


def coordinates(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        return [lat, lon] if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0, 0) else None
    except (TypeError, ValueError, OverflowError):
        return None


def point(row, role, label, prefix="", order=None):
    return {"role": role, "label": label, "position": coordinates(row.get(prefix + "latitude"), row.get(prefix + "longitude")), "public_key": row.get(prefix + "public_key"), "updated_at": row.get(prefix + "position_updated_at") if prefix else row.get("updated_at", row.get("last_seen")), "order": order}


def connection():
    db = sqlite3.connect(data.DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def bot_point(db):
    columns = {r["name"] for r in db.execute("PRAGMA table_info(companion_positions)")}
    if "is_bot" not in columns:
        return point({}, "bot", "Bot · position not recorded")
    bots = [dict(r) for r in db.execute("SELECT * FROM companion_positions WHERE is_bot = 1")]
    if len(bots) != 1:
        return point({}, "bot", "Bot · position missing or ambiguous")
    return point(bots[0], "bot", bots[0].get("name") or "Bot")


def repeater_map():
    with closing(connection()) as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM repeaters ORDER BY name COLLATE NOCASE, public_key")]
        nodes = [point(r, "repeater", r.get("name") or "Unnamed repeater") for r in rows]
        bot = bot_point(db)
        valid = [n for n in nodes if n["position"]]
        notes = [f"{len(valid)} of {len(rows)} repeaters have usable coordinates.", "Repeater and bot markers use their latest saved database positions."]
        if bot["position"]:
            valid.append(bot)
        else:
            notes.append("Bot position is not available. Restart the updated bot to save it.")
        return {"nodes": valid, "segments": [], "notes": notes, "hops": []}


def route_map(log_id):
    with closing(connection()) as db:
        record = db.execute("SELECT * FROM logger WHERE id = ?", (log_id,)).fetchone()
        if record is None:
            return None
        record = dict(record)
        rows = [dict(r) for r in db.execute("SELECT * FROM repeaters")]
        sender = point(record, "sender", record.get("sender") or "Sender", "sender_", 0)
        bot = bot_point(db)
        notes = ["Sender → numbered repeaters → bot. Lines show recorded hop order, not the physical radio signal path.", "Sender uses the snapshot saved with this command. Repeaters and bot use latest saved positions, which may differ for older commands."]
        if not sender["position"]:
            notes.append("No sender position snapshot in this entry; today's sender position is not substituted.")
        elif sender["updated_at"] is not None:
            notes.append("Sender position saved: " + data.timestamp(sender["updated_at"]))
            try:
                age = float(record["recv_time"]) - float(sender["updated_at"])
                notes.append(f"Sender position age at reception: {max(0, int(age)):,} seconds." if age >= 0 else "Sender position timestamp is later than reception; check the clocks.")
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
        if not bot["position"]:
            notes.append("Bot position is not available. Restart the updated bot to save it.")
        chain, hops = [sender], []
        path_valid = True
        try:
            raw = record.get("rx_path")
            count = int(record["path_len"])
            count = 0 if count == 255 else count & 63 if count > 63 else count
            if not 0 <= count <= 63:
                raise ValueError()
            # Missing RX metadata is acceptable only for an explicitly direct packet.
            if count == 0:
                if raw not in (None, "", b""):
                    raise ValueError()
                identifiers = []
            else:
                size = int(record["path_hash_size"])
                if size not in (1, 2, 3):
                    raise ValueError()
                path = bytes.fromhex(raw) if isinstance(raw, str) else bytes(raw)
                if len(path) != count * size:
                    raise ValueError()
                identifiers = [path[i:i + size].hex() for i in range(0, len(path), size)]
            for order, prefix in enumerate(identifiers, 1):
                matches = [r for r in rows if str(r.get("public_key") or "").lower().startswith(prefix)]
                node = point(matches[0], "repeater", matches[0].get("name") or prefix, order=order) if len(matches) == 1 else point({}, "repeater", prefix, order=order)
                state = "Resolved" if node["position"] else "Coordinates missing" if len(matches) == 1 else f"Ambiguous: {len(matches)} matches" if matches else "Unknown repeater"
                hops.append({"number": order, "hash": prefix, "name": node["label"], "status": state})
                chain.append(node)
            if not identifiers:
                notes.append("Direct packet: no repeater hops recorded.")
        except (KeyError, TypeError, ValueError, OverflowError):
            path_valid = False
            notes.append("Received path metadata is missing or invalid; no route connections can be drawn.")
            chain.append(point({}, "gap", "Missing path"))
        chain.append(bot)
        segments = [[a["position"], b["position"]] for a, b in zip(chain, chain[1:]) if a["position"] and b["position"]]
        if any(h["status"] != "Resolved" for h in hops):
            notes.append("Unknown, ambiguous or unlocated hops break the route line; no repeater is guessed.")
        direct = distance_km(sender["position"], bot["position"]) if sender["position"] and bot["position"] else None
        route = None
        incomplete = any(not node["position"] for node in chain)
        if direct is not None and path_valid:
            located = [node["position"] for node in chain if node["position"]]
            route = sum(distance_km(a, b) for a, b in zip(located, located[1:]))
            if incomplete:
                notes.append("Route distance is a lower bound through confirmed waypoints; unresolved hops are not guessed or connected on the map.")
        return {"nodes": [n for n in chain if n["position"]], "segments": segments, "hops": hops, "notes": notes,
                "direct_distance_km": direct, "route_distance_km": route,
                "route_distance_lower_bound": route is not None and incomplete,
                "path_valid": path_valid, "sender_name": sender["label"], "bot_name": bot["label"]}


def distance_km(start, end):
    lat1, lon1, lat2, lon2 = map(math.radians, (*start, *end))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(max(0.0, min(1.0, value))))
