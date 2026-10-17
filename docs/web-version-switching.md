# Updates, branch migration and rollback

## Stable branch

**MeshcoreStation 3.0.1** is the stable V3 release on **main**. The room server is
included. `feature/v3` and `feature/room-server` have been retired and removed
from GitHub; their commit histories are preserved in main.

## Update from the dashboard

1. Open **Settings → Updates / version**.
2. Select **main**. If needed, press **Check for updates** to refresh branch choices.
3. Press **Check for updates** with main selected and review the revision.
4. Press **Install update**, or **Switch to main** if running a former feature branch.
5. Wait for the dashboard to restart and reload.

An old installed branch can remain in the dropdown as the current selection even
though it no longer exists on GitHub. Checking that deleted branch will fail;
select main instead. Branches refresh on initial page load and **Check for
updates**, without an extra refresh button or repeated progress-poll discovery.

The updater checks the exact target and checkout cleanliness, backs up code and
data, and restores the previous installation if startup fails. When requirements
are unchanged it reuses the virtual environment without a dependency scan or pip
installation. Dependency changes trigger wheel preparation and environment backup.
Startup smoke and health checks still apply to both paths.

## Older installations without a working branch selector

Use the dashboard when possible. For manual migration, first stop the service and
back up the complete data directory and `meshcorestation.env`. Record the current
revision. With a clean checkout and no unpublished commits on the local main:

```bash
cd ~/MeshcoreStation
git status --short
git rev-parse HEAD
sudo systemctl stop meshcorestation
# Back up data/ and meshcorestation.env before continuing.
git fetch origin main
git switch main
git merge --ff-only FETCH_HEAD
git branch --set-upstream-to=origin/main main
bash install.sh
```

If no local main exists, use `git switch -c main FETCH_HEAD` instead of
`git switch main`. A clone restricted to a former feature branch may need
`git remote set-branches origin main` before fetching. Choose **Install / repair**
in the existing installation directory. Do not discard local changes or force
reset unpublished commits to make an update proceed.

## Recovery

Keep updater backups under `.updates/` until the installation works on your
hardware. The removed feature branches are not rollback targets. If recovery is
needed, stop the service and restore a matching saved installation, configuration
and data together. Never copy SQLite files while the station is writing them.

Switching to main does not disable rooms or remove their database. To stop room
traffic, disable the rooms in the room-server page. Application updates do not
flash the companion; companion firmware updates are a separate operation.

## Release version policy

Every published application update must increment `meshcorestation.__version__`
and update the current-version references in the README and guides. Queue several
changes under one release version; do not publish changed application code with
the same version as the previous release.

### 3.0.1

Expanded repeater configuration, an authenticated remote Console tab, and a
searchable command-picker popup with purpose explanations and editable placeholders.
