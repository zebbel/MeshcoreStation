#!/usr/bin/env python3
"""Render README screenshots from MeshcoreStation's real browser UI styles.

The screenshots use the project's actual CSS, logo, dashboard structure and
Commands dialog structure. Values are representative sample data so rendering
does not require a radio or a running MeshCore Companion.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "meshcorestation" / "web" / "assets"
OUTPUT = ROOT / "docs" / "images"


def chrome_binary() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit("No Chrome/Chromium executable found.")


def actual_css() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(ASSETS.glob("*.css")))


def logo_data_uri() -> str:
    payload = base64.b64encode((ASSETS / "meshcore-logo.png").read_bytes()).decode("ascii")
    return "data:image/png;base64," + payload


def dashboard_html(css: str, logo: str) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
<style>body {{ min-height: 100vh; }}</style>
</head>
<body>
<main class="shell">
  <header>
    <div class="brand">
      <div class="mark meshcore-mark"><img src="{logo}" alt="MeshCore" style="width:38px;height:38px;object-fit:contain"></div>
      <div><h1>MeshcoreStation</h1><p class="muted">Your mesh, at a glance.</p></div>
    </div>
    <div class="refresh-label"><span class="live-dot"></span> Refreshes every 5 seconds</div>
  </header>

  <div class="cards">
    <section class="card">
      <div class="card-heading">
        <p class="eyebrow">Bot status</p>
        <button class="info-button">Settings</button><button class="info-button">Scopes</button><button class="info-button">Commands</button>
      </div>
      <div class="metric running">Running</div>
      <p class="muted">Companion connected · channel meshcorestation</p>
    </section>

    <section class="card">
      <div class="card-heading"><p class="eyebrow">Known repeaters</p><button class="info-button">Map ↗</button></div>
      <div class="metric">42</div>
      <p class="muted">37 repeaters with usable coordinates</p>
    </section>

    <section class="card">
      <p class="eyebrow">Last command received</p>
      <div class="metric" id="last-command">ping</div>
      <p class="muted">@Alice · 2 hops · SNR 7.5 · RSSI -92 dBm</p>
    </section>
  </div>

  <section class="history">
    <div class="toolbar">
      <div><h2>Repeater battery</h2><p class="muted">Voltage history and scheduled channel reports</p></div>
      <button class="info-button">Battery history / settings</button>
    </div>
    <div style="padding:0 24px 22px">
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
        <div class="card" style="padding:15px"><p class="eyebrow">DB0XYZ</p><div class="metric" style="font-size:22px">4.08 V</div><p class="muted">Last sample 2 min ago</p></div>
        <div class="card" style="padding:15px"><p class="eyebrow">DB0ABC</p><div class="metric" style="font-size:22px">3.91 V</div><p class="muted">Last sample 6 min ago</p></div>
        <div class="card" style="padding:15px"><p class="eyebrow">DB0DEF</p><div class="metric" style="font-size:22px">3.76 V</div><p class="muted">Last sample 11 min ago</p></div>
      </div>
    </div>
  </section>

  <section class="history" style="margin-top:24px">
    <div class="toolbar">
      <div><h2>Command history</h2><p class="muted">Oldest to newest · Europe/Berlin</p></div>
      <div class="filter"><label>Command</label><div class="Select-control" style="height:36px;padding:8px 10px;border:1px solid var(--border);border-radius:4px">All commands</div></div>
    </div>
    <div class="list-tools"><button class="secondary">Load older</button><span class="muted">3 entries</span><button class="secondary" id="jump-latest">↓ Latest</button></div>
    <div id="command-scroll">
      <table>
        <thead><tr><th>Date &amp; time</th><th>Command</th><th>Received from</th><th>Details</th></tr></thead>
        <tbody>
          <tr><td class="date">07.10.2026 10:31:14</td><td class="command">ping</td><td>Alice</td><td><button>View details</button></td></tr>
          <tr><td class="date">07.10.2026 10:33:05</td><td class="command">status</td><td>Bob</td><td><button>View details</button></td></tr>
          <tr><td class="date">07.10.2026 10:36:42</td><td class="command">ping</td><td>Charlie</td><td><button>View details</button></td></tr>
        </tbody>
      </table>
    </div>
    <div class="updated muted">Updated just now</div>
  </section>
</main>
</body>
</html>"""


def commands_html(css: str, logo: str) -> str:
    base = dashboard_html(css, logo).replace("</body>", "")
    dialog = r"""
<dialog id="commands-dialog" aria-labelledby="commands-title">
  <div class="dialog-body">
    <div class="dialog-header"><h2 id="commands-title">Commands</h2><button type="button" aria-label="Close commands">×</button></div>
    <p class="muted">Add commands and define their help text and replies.</p>
    <div class="commands-toolbar"><button>Reload</button><button>＋ Add command</button></div>
    <ul id="commands-list">
      <li class="command-row"><strong class="command-name">?</strong><div class="command-description"><span class="command-badge">🔒 Required</span><p>Show available commands</p><code>{command_list}</code><small class="muted">Action: Reply</small></div><div class="command-actions"><button>Edit</button></div></li>
      <li class="command-row"><strong class="command-name">status</strong><div class="command-description"><p>Show repeater count</p><code>@{sender_name} | {repeater_count} repeaters.</code><small class="muted">Action: Reply</small></div><div class="command-actions"><button>Edit</button><button class="command-delete">Delete</button></div></li>
      <li class="command-row"><strong class="command-name">ping</strong><div class="command-description"><p>Test the connection</p><code>@{sender_name} | {hop_count} hops | SNR {snr} | RSSI {rssi} dBm | direct {direct_distance}km | route {route_distance}km | scope {scope_name}.</code><small class="muted">Action: Reply</small></div><div class="command-actions"><button>Edit</button><button class="command-delete">Delete</button></div></li>
    </ul>
    <section class="commands-preview"><h3>Help reply preview</h3><pre>?: Show available commands | status: Show repeater count | ping: Test the connection</pre><p class="muted">Built from each command’s help text. Preview only; nothing is sent to the mesh.</p></section>
  </div>
  <div class="commands-footer"><div><p class="muted">? is always available and cannot be deleted or renamed.</p><span>All changes saved</span></div><button>Cancel</button><button disabled>Save changes</button></div>
</dialog>
<script>addEventListener("load", () => document.getElementById("commands-dialog").showModal());</script>
</body></html>
"""
    return base + dialog


def capture(chrome: str, html: str, name: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / f"{name}.html"
        source.write_text(html, encoding="utf-8")
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                "--window-size=1440,980",
                f"--screenshot={OUTPUT / (name + '.png')}",
                source.as_uri(),
            ],
            check=True,
        )


def main() -> None:
    chrome = chrome_binary()
    css = actual_css()
    logo = logo_data_uri()
    capture(chrome, dashboard_html(css, logo), "dashboard")
    capture(chrome, commands_html(css, logo), "commands")


if __name__ == "__main__":
    main()
