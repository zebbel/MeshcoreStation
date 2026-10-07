"""Validate contact edits and verify the companion contact list."""
import math
import re
from meshcore import EventType
from meshcorestation.radio.contact_details import details


def public_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("Public key must be exactly 64 hexadecimal characters")
    return value.lower()


def coordinate(value, label, limit):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit:
        raise ValueError(f"{label} must be a number between {-limit} and {limit}")
    return float(value)


def contact_view(contact):
    if not isinstance(contact, dict):
        raise ValueError("Invalid contact response")
    name, kind = contact.get("adv_name"), contact.get("type")
    if not isinstance(name, str) or type(kind) is not int:
        raise ValueError("Incomplete contact response")
    return {
        "public_key": public_key(contact.get("public_key")),
        "name": name,
        "type": kind,
        "latitude": coordinate(contact.get("adv_lat"), "Latitude", 90),
        "longitude": coordinate(contact.get("adv_lon"), "Longitude", 180),
    }


async def read_contacts(companion):
    info = await companion.get_self_info()
    if not isinstance(info, dict):
        raise RuntimeError("Could not identify the connected companion")
    identity = public_key(info.get("public_key"))
    result = await companion.mc.commands.get_contacts(lastmod=0)
    if result is None or result.type != EventType.CONTACTS or not isinstance(result.payload, dict):
        raise RuntimeError("Could not read contacts from the companion; refresh before retrying")
    contacts = [{**contact_view(contact), "details": details(contact, companion.database)} for contact in result.payload.values()]
    if len({contact["public_key"] for contact in contacts}) != len(contacts):
        raise RuntimeError("Duplicate keys in contact response; refresh before retrying")
    contacts.sort(key=lambda contact: (contact["name"].casefold(), contact["public_key"]))
    return {"public_key": identity, "contacts": contacts}


def new_contact(value):
    if not isinstance(value, dict) or not {"public_key", "name", "type"} <= value.keys():
        raise ValueError("Contact needs a full public key, name and type")
    if set(value) - {"public_key", "name", "type", "latitude", "longitude"}:
        raise ValueError("Unknown contact field")
    name, kind = value["name"], value["type"]
    if (not isinstance(name, str) or not name.strip() or len(name.encode("utf-8")) > 31 or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise ValueError("Name must contain 1-31 UTF-8 bytes without control characters")
    if type(kind) is not int or kind not in (1, 2):
        raise ValueError("Contact type must be 1 (Companion) or 2 (Repeater)")
    lat, lon = value.get("latitude"), value.get("longitude")
    if lat is None and lon is None:
        lat = lon = 0.0
    else:
        lat = coordinate(lat, "Latitude", 90)
        lon = coordinate(lon, "Longitude", 180)
    return {
        "public_key": public_key(value["public_key"]), "adv_name": name,
        "type": kind, "flags": 0, "out_path": "", "out_path_len": -1,
        "out_path_hash_mode": -1, "last_advert": 0, "adv_lat": lat, "adv_lon": lon,
    }


async def handle_contacts(companion, request):
    # CompanionControl.handle holds control_lock for the entire operation.
    operation = request.get("operation")
    if operation not in {"get_contacts", "add_contact", "delete_contact"}:
        raise ValueError("Unknown contact operation")
    before = await read_contacts(companion)
    if operation == "get_contacts":
        return {"ok": True, **before}
    if request.get("expected_public_key") != before["public_key"]:
        return {"ok": False, "error": "Companion changed. Refresh contacts before saving.", **before}

    existing = {contact["public_key"]: contact for contact in before["contacts"]}
    commands = companion.mc.commands
    if operation == "add_contact":
        contact = new_contact(request.get("value"))
        key = contact["public_key"]
        if key == before["public_key"]:
            raise ValueError("Cannot add the connected companion as its own contact")
        if key in existing:
            return {"ok": False, "error": "This public key is already a contact.", **before}
        result = await commands.add_contact(contact)
    else:
        key = public_key(request.get("public_key"))
        if request.get("confirm_delete") is not True:
            raise ValueError("Deleting a contact requires confirm_delete=true")
        if key not in existing:
            return {"ok": False, "error": "Contact no longer exists. Refresh the list.", **before}
        if request.get("expected") != {field: value for field, value in existing[key].items() if field != "details"}:
            return {"ok": False, "error": "Contact changed. Refresh and review before deleting.", **before}
        result = await commands.remove_contact(key)

    if result is None or result.type != EventType.OK:
        raise RuntimeError("Contact change was not acknowledged. Refresh contacts before retrying.")
    after = await read_contacts(companion)
    saved = next((item for item in after["contacts"] if item["public_key"] == key), None)
    verified = after["public_key"] == before["public_key"]
    if operation == "delete_contact":
        verified = verified and saved is None
        if verified:
            # meshcore 2.3.14 merges reads into its cache, retaining deleted entries.
            companion.mc.contacts.pop(key, None)
    else:
        verified = verified and saved is not None and all(
            saved[field] == contact[source] for field, source in
            (("name", "adv_name"), ("type", "type"))
        ) and all(
            math.isclose(saved[field], int(contact[source] * 1e6) / 1e6,
                         rel_tol=0, abs_tol=0.000001)
            for field, source in (("latitude", "adv_lat"), ("longitude", "adv_lon"))
        )
    response = {"ok": verified, **after}
    if not verified:
        response["error"] = "Contact change could not be verified. Refresh contacts before retrying."
    companion.logger.info("Companion contact operation %s: verified=%s", operation, verified)
    return response