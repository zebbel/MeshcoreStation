# MeshCore Netz Analyzer — V4 offline fixtures

This bundle was extracted from the **second Firefox HAR recording**, captured on **24 October 2026** while viewing **DE_HE_HP_RPT1** (`769b90b4dd327d7bc9cc651fb8d2f8a4a217957cd36feac6b3216b5acedc36ff`) near Heppenheim, Germany.

## What is verified

- Firefox recorded **HTTP 200** JSON responses for the eight endpoints in `manifest.json`. The response bodies are preserved in `responses/*.json` with their original fields and values (formatting changed only).
- The captured requests used ordinary `GET` and **did not contain Cookie or Authorization request headers**.
- These observations support implementing **offline parsers, UI mocks, snapshot tests, cache logic, and error handling**. They do **not** establish permission for automated third-party requests or guarantee the endpoint works from the MeshcoreStation server.
- Direct access from the development environment reportedly returns **HTTP 403 / Cloudflare error 1010**. **Do not bypass Cloudflare, forge browser identities, reuse captured browser headers as a circumvention measure, scrape around the block, or defeat access controls.** Treat the live source as unavailable there until the operator permits access by an approved method.

## Captured endpoints and response files

| HTTP method / path and query | Saved JSON file | Sample status |
| --- | --- | --- |
| `GET /api/nodes/{key}/detail?hours=24` | `responses/node_detail_24h.json` | 200 |
| `GET /api/nodes/{key}/neighbors` | `responses/node_neighbors.json` | 200 |
| `GET /api/nodes/{key}/reach?days=1` | `responses/node_reach_1d.json` | 200 |
| `GET /api/graph/metrics/{key}` | `responses/graph_metrics.json` | 200 |
| `GET /api/nodes/{key}/clock-skew?hours=24` | `responses/clock_skew_24h.json` | 200 |
| `GET /api/nodes/{key}/direct-packets?since=24` | `responses/direct_packets_24h_empty.json` | 200; empty `rows` |
| `GET /api/channels/beacons?hours=720&node={key}` | `responses/channel_beacons_720h_empty.json` | 200; empty `beacons` |
| `GET /api/channels/sensors?hours=720&node={key}` | `responses/channel_sensors_720h_empty.json` | 200; empty `readings` |

Substitute `{key}` with the 64-digit hexadecimal repeater public key **only when use of the live interface is authorized**.

## Confirmed response semantics — don't invent data

- `detail`: `node`, `stat`, `heardBy`, `timeline`, `packetTypes`, `hopDist`, `carriedTypes`, `hopTrend`, `recentPackets`, `pathsThroughNode`, `snrTrend`, `relayTimeline`, `relayNeighbours`, `relayRegions`, and other fields. In this capture: `stat.relayCount24h`=107, `stat.relayCount1h`=5, `stat.pairsServed`=21; `heardBy` is **empty**. There are 50 returned path patterns and 23 relay timeline buckets.
- `reach`: 16 entries in `neighbourList`, `twoWayCount`=4, `directObservers`=0. Directional `weHear`/`theyHear` are analyzer-derived counts, **not RSSI/SNR and not proof of a direct RF link**.
- `neighbors`: five inferred-only neighbors, `SNR`=null in these records. No direct signal measurements should be fabricated.
- `graph_metrics`: graph `degree` and betweenness/rank metrics. They are different concepts from radio link quality.
- `clock_skew`: `recentHashEvidence` has observer *counts*; it does not disclose those observers' individual identities or RSSI/SNR. `sampleCount`=0 in the capture.
- `direct_packets`: empty `rows`; code must handle this normally.
- Beacons and sensors: both empty in the capture; code must not mistake that for a network error.

These are **time-specific recordings**, not guarantees of present state. `stat.relayCount24h` is a **rolling window**, not a number to increment on every refresh. Route hash prefixes may be ambiguous or collide. RSSI/SNR of an observer hearing a multi-hop packet describes only the final radio hop.

## Implementation instructions for MeshcoreStation V4

1. Develop a separate, optional, read-only analyzer backend client with a **fixture/mock transport**. Do not hard-code the sample repeater key or names into production behavior; select repeater via existing managed-repeater selection.
2. Build the Network Monitoring UI from these recorded shapes: relay counts, reachability, inferred neighbors, path patterns, historical buckets, graph metrics. Label provenance and unknown fields clearly.
3. Load only when the Network Monitoring disclosure is opened. Cache the last successful results for **5 minutes**, show timestamp, manual Refresh, and stale results during errors. No background polling while closed.
4. Add retries **only for transient errors** with bounded backoff, and never automatically keep retrying 403/1010. Show a distinct `Remote analyzer blocked/unavailable` state; don't pretend API access works.
5. Validate safe URL construction: fixed HTTPS host, fixed path templates, strict **64-character hexadecimal public key**, query parameter allowlists, bounded response size/timeouts. No arbitrary URL proxy or SSRF vector.
6. Use fixture-driven regression tests for successful, empty, stale, malformed JSON, timeout, HTTP 403/1010, 429 and 503, repeater switch, stale-response races, and five-minute cache. Simulate faults; the actual captured responses in this bundle are all successful (some empty).
7. Keep the existing app fully usable when external monitoring is blocked. Do not claim live integration is verified or fully operational under Cloudflare 1010.
8. **Before describing live monitoring as supported in a production release, confirm permitted access via documented API terms, an operator-approved service endpoint, or another authorized source, and test from the target deployment environment.** If unavailable, treat the integration as experimental/offline or disabled, and disclose the limitation prominently.

## Privacy and handling

This bundle contains **JSON response bodies only**. It intentionally excludes original HAR network headers, cookies, authorization material, client IP data, and unrelated page assets. It **does contain public node identifiers, node names, and coordinates from the analyzer** because accurate parser testing needs those fields. Review these before distributing the fixtures beyond the project. Do not publish the original HAR files.

## Quick local validation

From the extracted folder:

```bash
python3 validate_fixtures.py
```

That script verifies the fixture shapes; it does **not** contact the live API.
