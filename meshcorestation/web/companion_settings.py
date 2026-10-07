"""Guard local HTTP control requests and dispatch validated operations."""
import ipaddress
import json
import os
import re
import socket
import threading
from pathlib import Path
from urllib.parse import urlsplit
from flask import jsonify, request
from meshcorestation.web.data import DB_PATH

CONTROL_LOCK = threading.Lock()
FIELDS = {"public_key", "name", "adv_lat", "adv_lon", "tx_power", "max_tx_power", "radio_freq", "radio_bw", "radio_sf", "radio_cr"}
NETWORK_FIELDS = {"public_key", "path_hash_size", "default_scope"}
NETWORK_OPERATIONS = {"path_hash_size", "default_scope"}
CONTACT_OPERATIONS = {"get_contacts", "add_contact", "delete_contact"}
CHANNEL_OPERATIONS = {"get_channels", "add_channel", "delete_channel", "set_bot_channel"}
CONTACT_FIELDS = {"public_key", "name", "type", "latitude", "longitude"}


def allowed_host(host):
    local = socket.gethostname().lower()
    names = {"localhost", "meshcorestation", "meshcorestation.local", "meshcore", "meshcore.local", local, local.split(".")[0] + ".local"}
    names.update(name.strip().lower() for name in os.getenv("MESHCORESTATION_CONTROL_HOSTS", "").split(",") if name.strip())
    if host in names:
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback
    except ValueError:
        return False


def bot_request(payload):
    # Waitress threads submit work to the single radio event loop.
    from meshcorestation.bridge import bridge
    result = bridge.request(payload)
    if not isinstance(result, dict) or type(result.get("ok")) is not bool:
        raise ValueError("Invalid bot response")
    if payload.get("operation") in CHANNEL_OPERATIONS:
        if result["ok"] and (
            not isinstance(result.get("public_key"), str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", result["public_key"])
            or not isinstance(result.get("revision"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", result["revision"])
            or type(result.get("capacity")) is not int
            or type(result.get("free_slots")) is not int
            or not isinstance(result.get("channels"), list)
            or any(not isinstance(item, dict) or not {"index", "name", "type", "protected"} <= item.keys()
                   for item in result["channels"])
        ):
            raise ValueError("Incomplete channels response")
        return result
    if payload.get("operation") in CONTACT_OPERATIONS:
        if result["ok"] and (
            not isinstance(result.get("public_key"), str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", result["public_key"])
            or not isinstance(result.get("contacts"), list)
            or any(not isinstance(item, dict) or not CONTACT_FIELDS <= item.keys()
                   for item in result["contacts"])
        ):
            raise ValueError("Incomplete contacts response")
        return result
    network_request = payload.get("operation") in NETWORK_OPERATIONS | {"get_network"}
    key, fields = ("network", NETWORK_FIELDS) if network_request else ("settings", FIELDS)
    if result["ok"] and (not isinstance(result.get(key), dict) or not fields <= result[key].keys()):
        raise ValueError("Incomplete settings response")
    return result


def register_companion_routes(server):
    @server.route("/api/repeater", methods=["POST"])
    @server.route("/api/bot/commands", methods=["GET", "POST"])
    @server.route("/api/bot/scopes", methods=["GET", "POST"])
    @server.route("/api/bot/voltage", methods=["GET", "POST"])
    @server.route("/api/bot/runtime", methods=["GET", "POST"])
    @server.route("/api/companion", methods=["GET", "POST"])
    @server.route("/api/companion/network", methods=["GET", "POST"])
    @server.route("/api/companion/contacts", methods=["GET", "POST"])
    @server.route("/api/companion/channels", methods=["GET", "POST"])
    def companion_settings_api():
        def reply(body, status=200):
            response = jsonify(body)
            response.status_code = status
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response

        host = urlsplit(request.host_url).hostname or ""
        origin = request.headers.get("Origin")
        if not allowed_host(host.lower()):
            return reply({"ok": False, "error": "Use the Pi hostname or the Pi's local IP for companion settings."}, 403)
        if request.headers.get("X-Meshcore-Control") != "1" or request.headers.get("Sec-Fetch-Site") == "cross-site":
            return reply({"ok": False, "error": "Open settings from this dashboard."}, 403)
        if origin and origin != request.host_url.rstrip("/"):
            return reply({"ok": False, "error": "Cross-origin settings requests are blocked."}, 403)

        if request.path == "/api/repeater":
            from meshcorestation.web.repeater_api import repeater_request
            if not CONTROL_LOCK.acquire(blocking=False):
                return reply({"ok": False, "error": "Another control request is running. Try again when it finishes."}, 409)
            try:
                body, status = repeater_request(request)
                return reply(body, status)
            finally:
                CONTROL_LOCK.release()

        if request.path == "/api/bot/commands":
            from meshcorestation.web.commands_api import commands_request
            body, status = commands_request(request)
            return reply(body, status)

        if request.path == "/api/bot/scopes":
            from meshcorestation.web.scopes_api import scopes_request
            body, status = scopes_request(request)
            return reply(body, status)

        if request.path == "/api/bot/voltage":
            from meshcorestation.web.voltage_api import voltage_request
            body, status = voltage_request(request)
            return reply(body, status)

        if request.path == "/api/bot/runtime":
            from meshcorestation.web.bot_runtime import runtime_request
            if not CONTROL_LOCK.acquire(blocking=False):
                return reply({"ok": False, "error": "Another control request is running. Try again."}, 409)
            try:
                body, status = runtime_request(request)
                return reply(body, status)
            finally:
                CONTROL_LOCK.release()

        is_network = request.path.endswith("/network")
        is_channels = request.path.endswith("/channels")
        is_contacts = request.path.endswith("/contacts")
        payload = {"operation": "get_channels" if is_channels else "get_contacts" if is_contacts else "get_network" if is_network else "get"}
        if request.method == "POST":
            if request.mimetype != "application/json":
                return reply({"ok": False, "error": "Expected JSON."}, 415)
            try:
                raw = request.stream.read(16385)
                if len(raw) > 16384:
                    raise ValueError("Request too large")
                payload = json.loads(raw)
                operations = {"add_channel", "delete_channel", "set_bot_channel"} if is_channels else {"add_contact", "delete_contact"} if is_contacts else NETWORK_OPERATIONS if is_network else {"name", "position", "tx_power", "radio"}
                fields = NETWORK_FIELDS if is_network else FIELDS
                if not isinstance(payload, dict) or payload.get("operation") not in operations:
                    raise ValueError("Unknown settings operation")
                if is_channels:
                    if any(not isinstance(payload.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", payload[key])
                           for key in ("expected_public_key", "expected_revision")):
                        raise ValueError("Refresh channels before saving")
                    if payload["operation"] == "add_channel" and not isinstance(payload.get("value"), dict):
                        raise ValueError("Missing channel")
                    if payload["operation"] == "set_bot_channel" and (type(payload.get("index")) is not int or not 0 <= payload["index"] <= 254):
                        raise ValueError("Invalid bot channel")
                    if payload["operation"] == "delete_channel" and (
                        payload.get("confirm_delete") is not True or type(payload.get("index")) is not int
                        or not 0 <= payload["index"] <= 254
                    ):
                        raise ValueError("Refresh and confirm deletion")
                elif is_contacts:
                    if not isinstance(payload.get("expected_public_key"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", payload["expected_public_key"]):
                        raise ValueError("Refresh contacts before saving")
                    if payload["operation"] == "add_contact" and not isinstance(payload.get("value"), dict):
                        raise ValueError("Missing contact")
                    if payload["operation"] == "delete_contact" and (
                        payload.get("confirm_delete") is not True
                        or not isinstance(payload.get("public_key"), str)
                        or not re.fullmatch(r"[0-9a-fA-F]{64}", payload["public_key"])
                        or not isinstance(payload.get("expected"), dict)
                        or set(payload["expected"]) != CONTACT_FIELDS
                    ):
                        raise ValueError("Refresh and confirm deletion")
                elif not isinstance(payload.get("expected"), dict) or set(payload["expected"]) != fields:
                    raise ValueError("Reload settings before saving")
                if payload["operation"] == "radio" and payload.get("confirm_radio_change") is not True:
                    raise ValueError("Confirm the radio change first")
                if is_network and (payload.get("confirm_network_change") is not True or "value" not in payload):
                    raise ValueError("Confirm the network change first")
                json.dumps(payload, allow_nan=False)
            except (ValueError, TypeError):
                return reply({"ok": False, "error": "Invalid request. Reload settings and check the entered values."}, 400)

        if not CONTROL_LOCK.acquire(blocking=False):
            return reply({"ok": False, "error": "Another settings request is running. Wait, then reload."}, 409)
        try:
            result = bot_request(payload)
            return reply(result, 200 if result["ok"] else 409)
        except FileNotFoundError:
            return reply({"ok": False, "error": "MeshcoreStation companion is offline. Check the selected serial port."}, 503)
        except PermissionError:
            return reply({"ok": False, "error": "Companion access denied. Check serial permissions."}, 503)
        except (OSError, ValueError):
            return reply({"ok": False, "error": "The bot response could not be confirmed. A submitted change may have applied. Reload before retrying."}, 503)
        finally:
            CONTROL_LOCK.release()