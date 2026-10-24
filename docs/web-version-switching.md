# V4 updates and recovery

MeshcoreStation 4.0.0 uses `v4.0.0`; V3 stays on `main`. Do not merge the
V4 branch into main without separate authorization.

## Update from the dashboard

1. Open **Settings → Updates / version**.
2. Select **v4.0.0**. If needed, press **Check for updates** to refresh branch choices.
3. Press **Check for updates** with v4.0.0 selected and review the revision.
4. Press **Install update**, or **Switch to v4.0.0** if running a former feature branch.
5. Wait for the dashboard to restart and reload.

An old installed branch can remain in the dropdown as the current selection even
though it no longer exists on GitHub. Checking that deleted branch will fail;
select v4.0.0 instead. Branches refresh on initial page load and **Check for
updates**, without an extra refresh button or repeated progress-poll discovery.

The updater checks the exact target and checkout cleanliness, backs up code and
data, and restores the previous installation if startup fails. When requirements
are unchanged it reuses the virtual environment without a dependency scan or pip
installation. Dependency changes trigger wheel preparation and environment backup.
Startup smoke and health checks still apply to both paths.

## Older installations without a working branch selector

Use the dashboard when possible. For manual migration, first stop the service and
back up the complete data directory and `meshcorestation.env`. Record the current
revision. With a clean checkout and no unpublished commits on the local destination branch:

```bash
cd ~/MeshcoreStation
git status --short
git rev-parse HEAD
sudo systemctl stop meshcorestation
# Back up data/ and meshcorestation.env before continuing.
git fetch origin v4.0.0
git switch v4.0.0
git merge --ff-only FETCH_HEAD
git branch --set-upstream-to=origin/v4.0.0 v4.0.0
bash install.sh
```

If no local v4.0.0 exists, use `git switch -c v4.0.0 FETCH_HEAD` instead of
`git switch v4.0.0`. A clone restricted to a former feature branch may need
`git remote set-branches origin v4.0.0` before fetching. Choose **Install / repair**
in the existing installation directory. Do not discard local changes or force
reset unpublished commits to make an update proceed.

## Recovery

Keep updater backups under `.updates/` until the installation works on your
hardware. The removed feature branches are not rollback targets. If recovery is
needed, stop the service and restore a matching saved installation, configuration
and data together. Never copy SQLite files while the station is writing them.

Switching to v4.0.0 does not disable rooms or remove their database. To stop room
traffic, disable the rooms in the room-server page. Application updates do not
flash the companion; companion firmware updates are a separate operation.
