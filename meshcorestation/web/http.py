"""Shared local-dashboard request policy and uncached JSON responses."""
import ipaddress
import os
import socket
from urllib.parse import urlsplit
from flask import jsonify, request


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


def control_request_error():
    """Return a rejection reason, or None for a trusted dashboard request."""
    if not allowed_host((urlsplit(request.host_url).hostname or '').lower()):
        return "Use the Pi hostname or the Pi's local IP for companion settings."
    if request.headers.get('X-Meshcore-Control') != '1' or request.headers.get('Sec-Fetch-Site') == 'cross-site':
        return 'Open settings from this dashboard.'
    origin = request.headers.get('Origin')
    if origin and origin != request.host_url.rstrip('/'):
        return 'Cross-origin settings requests are blocked.'
    return None


def json_response(body, status=200):
    response = jsonify(body)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
