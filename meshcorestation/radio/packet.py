"""Normalize only actual received channel packet evidence; no collection database."""
import hashlib
import re
def normalize(rx):
    try:
        route_type, kind = (int(rx['route_type']), int(rx['payload_type']))
        if route_type not in (0, 1) or kind == 9 or (not 0 <= kind <= 15):
            return None
        count, size = (int(rx['path_len']), int(rx['path_hash_size']))
        raw = rx['path']
        if not isinstance(raw, (str, bytes, bytearray)):
            return None
        raw = bytes.fromhex(raw) if isinstance(raw, str) else bytes(raw)
        if size not in (1, 2, 3) or not 0 <= count <= 63 or len(raw) != count * size or (len(raw) > 64):
            return None
        payload = rx.get('pkt_payload')
        digest = None
        if isinstance(payload, (bytes, bytearray)) and 0 < len(payload) <= 1024:
            digest = hashlib.sha256(bytes([kind]) + bytes(payload)).hexdigest()
        rssi = rx.get('rssi', rx.get('last_rssi'))
        snr = rx.get('snr', rx.get('last_snr'))
        return {'path': [raw[i:i + size].hex() for i in range(0, len(raw), size)], 'hash_size': size, 'kind': kind, 'scoped': int(route_type == 0), 'digest': digest, 'rssi': float(rssi) if type(rssi) in (int, float) and -300 < rssi < 50 else None, 'snr': float(snr) if type(snr) in (int, float) and -100 < snr < 100 else None}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
