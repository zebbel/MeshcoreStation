# Version switching and rollback

## Branches

| Branch | Purpose |
| --- | --- |
| `main` | Existing stable application |
| `feature/room-server` | Room-server version |
| `feature/v3` | V3 testing, based on room-server 2.8.0rc9 |

## First entry into V3 from the web app

1. On `feature/room-server`, open **Settings → Updates / version**.
2. Check for updates and install the room-server update **2.8.0rc10** or newer.
3. After the dashboard reloads, press **Check for updates** to refresh branches.
4. Select **feature/v3**, press **Check for updates** again, review the target,
   and install. The dashboard reloads into **3.0.0a1**.

The selector update is published on `feature/room-server`; an older `main`
installation must first switch to and update the room-server branch. Keep the
updater's backup until you have tested V3 with your companion and Android app.

## Updates while on V3

In **Settings → Updates / version**, select **feature/v3**, check for updates,
review the commit, and install. The selector loads all GitHub branch names on initial load and when you click
**Check for updates**; progress polling does not refresh the remote list. Branch
listing does not guarantee installability: the selected revision must pass the
web-switch compatibility check. A listing error retains the current selection. The updater checks the exact target, backs up data and dependencies,
and rolls back if application startup fails. Radio functionality still needs a
hardware check. Dashboard reload follows a successful revision change.

The updater refuses local edits and conflicting unpublished commits. It retains
backup files under `.updates/`. Keep enough disk space and do not run parallel
package-management jobs.

## Return path

To leave V3, select **feature/room-server** or **main** in V3's version
selector, check and install. Stable does not run the room server but retains its
database. This V3 refactor does not destructively migrate either database.

The updated room-server selector also offers V3 for re-entry. If dashboard startup
fails, stop the service and restore the saved installation, configuration and data
as a unit. Never copy SQLite files while the station is writing them.

Promotion to `main` happens only after review and hardware testing; creating the
V3 branch is not approval to merge it into stable.
