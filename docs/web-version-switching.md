# Switch versions from the dashboard

First update the stable installation to **2.7.9** using the existing web updater.
After the dashboard reloads, open **Settings → Updates / version**.

1. Select **Stable** or **Room server (experimental)**.
2. Click **Check for updates** and review the selected version.
3. Click **Install update** or **Switch to…**, then confirm.
4. Wait for the service to restart and the dashboard to reload automatically.

Stable follows `main`; Room server follows `feature/room-server`. Checks and
subsequent updates follow the selected branch. Switching back to Stable stops the
room server and keeps `data/rooms.db`, including room identities, members and posts.
Returning to the experimental branch resumes enabled rooms with their saved data.

The updater backs up data and settings, reuses validated unchanged dependencies,
and restores the previous branch and revision if startup verification fails.
Local source changes or unpublished destination-branch commits block a switch.
Both branches must retain the selector; switching to a release without it is
refused to preserve the web-based return path.

The experimental room server requires hardware testing with Android and your mesh.
It is disabled until you create and enable a room. Stable contains the version
selector but does not activate or include the experimental room runtime.
