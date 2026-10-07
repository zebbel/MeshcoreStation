"""Read and change path hash and flood scope settings with verification."""
import hashlib
import re
from meshcore import EventType
from meshcore.packets import CommandType


async def read_network(companion):
    info = await companion.get_self_info()
    if not isinstance(info, dict) or not info.get("public_key"):
        raise RuntimeError("Could not identify the connected companion")

    network = {"public_key": info["public_key"], "path_hash_size": None, "default_scope": None}
    warnings = []

    try:
        result = await companion.mc.commands.send_device_query()
        if result is None or result.type != EventType.DEVICE_INFO:
            raise ValueError("No device information response")
        mode = (result.payload or {}).get("path_hash_mode")
        if type(mode) is not int or mode not in (0, 1, 2):
            raise ValueError("Firmware did not report a supported path hash mode")
        network["path_hash_size"] = mode + 1
    except Exception as exc:
        warnings.append(f"Path hash size unavailable: {exc}")

    try:
        result = await companion.mc.commands.get_default_flood_scope()
        if result is None or result.type != EventType.DEFAULT_FLOOD_SCOPE or not isinstance(result.payload, dict):
            raise ValueError("No default scope response")
        scope = result.payload
        if not scope:
            network["default_scope"] = {"name": name.removeprefix("#"), "key": key.lower()}
        else:
            name, key = scope.get("scope_name"), scope.get("scope_key")
            if not isinstance(name, str) or not name or not isinstance(key, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", key):
                raise ValueError("Invalid default scope response")
            network["default_scope"] = {"name": name, "key": key.lower()}
    except Exception as exc:
        warnings.append(f"Default scope unavailable: {exc}")

    return network, warnings


def scope_packet(value):
    command = bytes([CommandType.SET_DEFAULT_FLOOD_SCOPE.value])
    if value is None or value == "":
        return command, {"name": "", "key": ""}
    if not isinstance(value, str):
        raise ValueError("Region scope must be a name or an empty string for unscoped")

    name = value.strip().removeprefix("#")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,29}", name):
        raise ValueError("Use 1-29 letters, digits, hyphens or underscores, optionally prefixed with #")

    encoded = name.encode("ascii")
    key = hashlib.sha256(("#" + name).encode("ascii")).digest()[:16]
    return command + encoded.ljust(31, b"\0") + key, {"name": name, "key": key.hex()}


async def handle_network(companion, request):
    operation = request.get("operation")
    if operation not in {"get_network", "path_hash_size", "default_scope"}:
        raise ValueError("Unknown network operation")

    before, warnings = await read_network(companion)
    if operation == "get_network":
        return {"ok": True, "network": before, "warnings": warnings}
    if request.get("expected") != before:
        return {"ok": False, "error": "Network settings changed. Read them again before saving.", "network": before, "warnings": warnings}
    if before[operation] is None:
        raise ValueError("This setting is unavailable. Check firmware support and read it again.")
    if request.get("confirm_network_change") is not True:
        raise ValueError("Network changes require confirm_network_change=true")
    if "value" not in request:
        raise ValueError("Missing setting value")

    value = request["value"]
    commands = companion.mc.commands

    if operation == "path_hash_size":
        if type(value) is not int or value not in (1, 2, 3):
            raise ValueError("Path hash size must be 1, 2 or 3 bytes")
        wanted = value
        result = await commands.set_path_hash_mode(value - 1)
    else:
        packet, wanted = scope_packet(value)
        result = await commands.send(packet, [EventType.OK, EventType.ERROR])

    if result is None or result.type != EventType.OK:
        raise RuntimeError("Network change was not acknowledged. Read settings again before retrying.")

    after, warnings = await read_network(companion)
    verified = after["public_key"] == before["public_key"] and after[operation] == wanted
    response = {"ok": verified, "network": after, "warnings": warnings}
    if not verified:
        response["error"] = "Network change could not be verified. Read settings again before retrying."

    companion.logger.info("Companion network setting %s: verified=%s", operation, verified)
    return response