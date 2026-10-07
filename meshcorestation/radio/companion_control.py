"""Validate settings, write them to the radio, and verify readback."""

import math
from meshcorestation.radio.repeater_control import RepeaterControl
from meshcorestation.radio.network_control import handle_network
from meshcorestation.radio.contacts_control import handle_contacts
from meshcorestation.radio.channels_control import handle_channels

from meshcore import EventType

FIELDS = ("public_key", "name", "adv_lat", "adv_lon", "tx_power", "max_tx_power", "radio_freq", "radio_bw", "radio_sf", "radio_cr",)


class CompanionControl:
    def __init__(self, companion):
        # Runtime dispatch holds the companion lock before invoking execute().
        self.companion = companion
        self.repeaters = RepeaterControl(companion)

    async def read(self):
        info = await self.companion.get_self_info()

        if (not isinstance(info, dict) or any(key not in info for key in FIELDS)):
            raise RuntimeError("Could not read complete companion settings")

        return {key: info[key] for key in FIELDS}

    @staticmethod
    def number(value, label, low, high, integer=False):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number")

        if (not low <= value <= high or (integer and value != int(value))):
            raise ValueError(f"Invalid {label}: expected {low} to {high}")

        return int(value) if integer else float(value)

    async def execute(self, request):
        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object")

        operation = request.get("operation")
        if operation == "repeater":
            return await self.repeaters.execute(request)
        if operation in {"get_contacts", "add_contact", "delete_contact"}:
            return await handle_contacts(self.companion, request)
        if operation in {"get_channels", "add_channel", "delete_channel", "set_bot_channel"}:
            return await handle_channels(self.companion, request)
        if operation in {"get_network", "path_hash_size", "default_scope"}:
            return await handle_network(self.companion, request)
        
        before = await self.read()

        if operation == "get":
            return {"ok": True, "settings": before}

        if operation not in {"name", "position", "tx_power", "radio"}:
            raise ValueError("Unknown operation")

        if request.get("expected") != before:
            return { "ok": False, "error": "Settings changed; review and try again", "settings": before, }

        commands = self.companion.mc.commands
        value = request.get("value")

        if operation == "name":
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value.encode("utf-8")) > 31
                or any(ord(c) < 32 or ord(c) == 127 for c in value)
            ):
                raise ValueError("Name must contain 1-31 UTF-8 bytes, " "without control characters")

            wanted = {"name": value}
            method, args = commands.set_name, (value,)

        elif operation == "position":
            if (not isinstance(value, dict) or set(value) != {"latitude", "longitude"}):
                raise ValueError("Position needs latitude and longitude")

            lat = self.number(value["latitude"], "latitude", -90, 90)
            lon = self.number(value["longitude"], "longitude", -180, 180)
            lat = int(lat * 1e6) / 1e6
            lon = int(lon * 1e6) / 1e6

            if (lat, lon) == (0, 0):
                raise ValueError("This bot treats 0,0 as a missing position")

            wanted = {"adv_lat": lat, "adv_lon": lon}
            method, args = commands.set_coords, (lat, lon)

        elif operation == "tx_power":
            power = self.number(value, "TX power", 0, before["max_tx_power"], True)
            wanted = {"tx_power": power}
            method, args = commands.set_tx_power, (power,)

        else:
            if request.get("confirm_radio_change") is not True:
                raise ValueError("Radio changes require confirm_radio_change=true")

            if (not isinstance(value, dict) or set(value) != {"freq", "bw", "sf", "cr"}):
                raise ValueError("Radio needs freq, bw, sf and cr")

            freq = self.number(value["freq"], "frequency MHz", 150, 2500)
            bw = self.number(value["bw"], "bandwidth kHz", 7.8, 500)
            sf = self.number(value["sf"], "spreading factor", 5, 12, True)
            cr = self.number(value["cr"], "coding rate", 5, 8, True)
            freq = int(freq * 1000) / 1000
            bw = int(bw * 1000) / 1000

            wanted = { "radio_freq": freq, "radio_bw": bw, "radio_sf": sf, "radio_cr": cr, }
            method, args = commands.set_radio, (freq, bw, sf, cr)

        result = await method(*args)

        if result is None or result.type != EventType.OK:
            raise RuntimeError("Change was not acknowledged; its outcome is unconfirmed")

        after = await self.read()
        verified = all(
            math.isclose(
                after[key], target, rel_tol=0, abs_tol=0.000002
            )
            if type(target) is float
            else after[key] == target
            for key, target in wanted.items()
        )

        response = {"ok": verified, "settings": after}

        if not verified:
            response["error"] = ("Readback differs from requested settings")

        if operation in {"name", "position"}:
            try:
                lat = self.number(after["adv_lat"], "latitude", -90, 90)
                lon = self.number(after["adv_lon"], "longitude", -180, 180)

                if (lat, lon) == (0, 0):
                    raise ValueError("No valid saved position")

                self.companion.database.save_companion_position(after["public_key"], after["name"], lat, lon, None, is_bot=True,)

            except Exception as exc:
                response["warning"] = ("Device readback succeeded, " f"but database sync failed: {exc}")

        self.companion.logger.info("Companion setting %s: verified=%s", operation, verified,)
        return response