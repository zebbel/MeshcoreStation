#!/usr/bin/env python3
"""Offline fixture checks; performs no network access."""
from pathlib import Path
import json
import re

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
key = manifest['repeater_public_key']
assert re.fullmatch(r'[a-f0-9]{64}', key)
entries = {p['file']:p for p in manifest['entries']}
assert len(entries) == 8
payloads = {}
for name,record in entries.items():
    assert record['method'] == 'GET' and record['recorded_status'] == 200
    assert key in record['path'] or 'node='+key in record['query']
    payloads[name.split('/')[-1]] = json.loads((root / name).read_text(encoding='utf-8'))
assert payloads['node_detail_24h.json']['node']['id'] == key
assert payloads['node_detail_24h.json']['stat']['relayCount24h'] == 107
assert len(payloads['node_detail_24h.json']['pathsThroughNode']) == 50
assert payloads['node_detail_24h.json']['heardBy'] == []
assert len(payloads['node_reach_1d.json']['neighbourList']) == 16
assert payloads['node_reach_1d.json']['twoWayCount'] == 4
assert payloads['node_reach_1d.json']['directObservers'] == 0
assert len(payloads['node_neighbors.json']) == 5
assert all(n['Provenance'] == 'inferred-only' and n['SNR'] is None for n in payloads['node_neighbors.json'])
assert payloads['direct_packets_24h_empty.json']['rows'] == []
assert payloads['channel_beacons_720h_empty.json']['beacons'] == []
assert payloads['channel_sensors_720h_empty.json']['readings'] == []
print('PASS: eight captured 200 JSON fixtures, key match, shapes and sample counts; no live network access')
