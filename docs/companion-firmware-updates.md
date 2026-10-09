# Companion firmware updates

Settings → Companion firmware checks published releases in `zebbel/MeshCore`.
Only the **Heltec V4 OLED USB** target is supported. Firmware compilation stays
in VS Code/PlatformIO. No releases are created or firmware flashed automatically.

## Publish a compatible release

Build `heltec_v4_companion_radio_usb` in the MeshCore checkout, then run this
helper from the MeshcoreStation checkout (paths can be absolute):

```sh
python3 scripts/package_companion_firmware.py /path/to/MeshCore/.pio/build/heltec_v4_companion_radio_usb /tmp/heltec-release
```

Attach both generated files to a GitHub release in `zebbel/MeshCore`:
`heltec_v4_companion_radio_usb.json` and `heltec_v4_companion_radio_usb.bin`.
Use an identifiable version/tag for each build. Prereleases are supported and
labelled. Do not package another target under this name. The manifest describes
the chip, target, application offset, image SHA-256, and partition-table SHA-256.
Checksums detect corruption; trust comes from the configured release repository.

## Install from the dashboard

Update MeshcoreStation first so its pinned esptool dependency is installed.
Connect the companion, check firmware releases, select one, and confirm the
hardware. Installed version/build/model comes from the radio's device query;
custom builds may report the same version even with different code.

The app downloads and validates the firmware, pauses its radio session, releases
USB, backs up all 16 MB of flash, and checks the installed partition table against
the build. It writes only the first application partition at `0x10000` and uses
esptool's write verification. Bootloader, partition table, identity, contacts,
channels and filesystem are not written. Changed partition layouts and devices
with noninitial OTA slot selection are rejected and require manual migration.
Radio service reconnects automatically; a failure to reconnect is reported
separately from successful flashing. Logs remain visible after closing Settings.

Backups (which include private device identity) are stored under
`DATA_DIR/firmware-backups/<timestamp>/` in a private directory. Retain them until
the new firmware works. No automatic rollback or power-loss recovery is claimed.
To recover a damaged app, use the saved backup with esptool on the Pi or a PC;
a full backup restore writes configuration too and must target the same device.

Automatic bootloader entry depends on the USB connection. If it fails, hold BOOT,
tap RESET, release BOOT, and use a manual esptool update; reconnect the running
companion before retrying in the dashboard. USB re-enumeration can change the port:
check Settings if reconnection fails. Do not disconnect power during flashing.

Station updates and companion updates share a lock, so a dashboard Station
update cannot restart the service while a firmware job is running. External
service restarts/power loss can interrupt a job; the next startup reports this.
