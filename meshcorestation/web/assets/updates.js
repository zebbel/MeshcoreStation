(() => {
    let panel, busy = false, checking = null, polling = null;
    const pageRevision = document.querySelector('meta[name="meshcorestation-revision"]')?.content;
    let reloading = false, selectedBranch = null, pageBranch = null;
    let labels = Object.create(null);
    const label = branch => labels[branch] || branch || 'unknown';
    function branchOptions() {
        const names = new Set([...Object.keys(labels), pageBranch, selectedBranch].filter(Boolean));
        panel.querySelector('.update-branch').replaceChildren(...[...names].sort().map(name => {
            const option = document.createElement('option');
            option.value = name; option.textContent = label(name);
            return option;
        }));
        panel.querySelector('.update-branch').value = selectedBranch;
    }
    async function refreshBranches() {
        try {
            const result = await api({action: 'branches'});
            labels = Object.assign(Object.create(null), result.branches || {});
            branchOptions();
            panel.querySelector('.update-branch-note').textContent = 'Branches loaded from GitHub. Check the selected branch before installing.';
        } catch (error) {
            panel.querySelector('.update-branch-note').textContent = 'Branch list unavailable: ' + error.message + ' You can retry; the current selection is retained.';
        }
    }
    const active = new Set(['queued', 'preparing', 'backing_up', 'installing', 'verifying', 'rolling_back']);
    async function api(body) {
        const response = await fetch('/api/update', {method: body ? 'POST' : 'GET', cache: 'no-store',
            headers: {'X-Meshcore-Control': '1', 'Content-Type': 'application/json'},
            ...(body ? {body: JSON.stringify(body)} : {}), signal: AbortSignal.timeout(body ? 130000 : 10000)});
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'Update request failed.');
        return result;
    }
    function message(text) { panel.querySelector('.update-message').textContent = text; }
    function buttons() {
        panel.querySelector('.update-check').disabled = busy || !selectedBranch;
        panel.querySelector('.update-branch').disabled = busy;
        panel.querySelector('.update-install').textContent = selectedBranch && selectedBranch !== pageBranch ? 'Switch to ' + label(selectedBranch) : 'Install update';
        panel.querySelector('.update-install').disabled = busy || !checking?.available || !checking?.ready || (checking.branch || 'main') !== selectedBranch;
    }
    function render(result) {
        if (pageBranch === null) pageBranch = result.branch || 'main';
        if (selectedBranch === null) selectedBranch = result.branch || null;
        branchOptions();
        checking = {...(result.check || {})};
        checking.ready = result.ready;
        panel.querySelector('.update-version').textContent = `Installed: ${result.version} (${result.revision.slice(0, 8)}) · ${label(result.branch)}`;
        panel.querySelector('.update-latest').textContent = checking.latest ? `Latest checked (${label(checking.branch)}): ${checking.latest_version} (${checking.latest.slice(0, 8)}) · ${window.meshcorestationFormatDate(checking.checked_at)}` : 'No update check yet.';
        const link = panel.querySelector('.update-changes');
        link.hidden = !checking.changes_url;
        if (checking.changes_url) link.href = checking.changes_url;
        const state = result.status || {};
        busy = active.has(state.phase);
        message(state.message || (result.ready ? 'Check GitHub for a newer version.' : 'One-time setup needed: run meshcorestation update in the Pi terminal.'));
        const progress = panel.querySelector('.update-progress');
        if (progress) progress.textContent = (state.elapsed_seconds !== undefined ? 'Step elapsed: ' + state.elapsed_seconds + 's\n' : '') + (state.log || '');
        panel.querySelector('.update-reload').hidden = state.phase !== 'complete';
        buttons();
        if (!reloading && state.phase === 'complete' && state.target === result.revision && pageRevision && pageRevision !== 'unknown' && (pageRevision !== result.revision || pageBranch !== (result.branch || 'main'))) {
            reloading = true;
            message('Update complete. Reloading the dashboard…');
            location.reload();
        }
        if (busy) startPolling();
        else if (polling) { clearInterval(polling); polling = null; }
    }
    let fetching = false;
    function startPolling() {
        if (polling) return;
        polling = setInterval(async () => {
            if (fetching) return;
            fetching = true;
            try { render(await api()); }
            catch (_) { message('The dashboard is restarting or temporarily unreachable. Waiting to reconnect…'); }
            finally { fetching = false; }
        }, 4000);
    }
    async function check() {
        busy = true; buttons(); message('Checking GitHub…');
        try {
            await refreshBranches();
            await api({action: 'check', branch: selectedBranch});
            render(await api());
            message(checking.available ? (checking.ready ? 'An update is available. Review changes, then install.' : 'Update available. Run meshcorestation update once in the terminal to enable web installation.') : 'You are up to date.');
        } catch (error) { message(error.message); }
        finally { busy = false; buttons(); }
    }
    async function install() {
        if (!checking?.available || (checking.branch || 'main') !== selectedBranch || !window.confirm(`Install ${checking.latest_version} (${checking.latest.slice(0, 8)}) from ${label(selectedBranch)}?\n\nMeshcoreStation will stop briefly. Code, settings, database and dependencies will be backed up. The previous installation will be restored if startup fails.`)) return;
        busy = true; buttons(); message('Submitting update…');
        try { render(await api({action: 'install', target: checking.latest, branch: selectedBranch})); startPolling(); }
        catch (error) {
            // A response can be lost when the worker stops the web process. Do not submit twice.
            message(`${error.message} Checking whether the update started…`); startPolling();
        }
    }
    function attach() {
        const dialog = document.getElementById('companion-dialog');
        if (!dialog || panel) return;
        panel = document.createElement('section'); panel.id = 'update-panel'; panel.className = 'companion-section';
        panel.innerHTML = '<h3>Updates / version</h3><label>Branch <select class="update-branch"></select></label><p class="update-branch-note muted">Loading branches from GitHub…</p><p class="muted">All repository branches are listed. Check compatibility and changes before installing a different branch.</p><p class="update-version muted"></p><p class="update-latest muted"></p><p>Updates come from zebbel/MeshcoreStation on GitHub. Backups are kept on this Pi.</p><div class="companion-toolbar"><button type="button" class="update-check">Check for updates</button><button type="button" class="update-install" disabled>Install update</button><a class="update-changes" target="_blank" rel="noopener noreferrer" hidden>View changes on GitHub ↗</a><button type="button" class="update-reload" hidden>Reload dashboard</button></div><p class="update-message" role="status" aria-live="polite"></p><details><summary>Update progress</summary><pre class="update-progress" style="white-space:pre-wrap;max-height:180px;overflow:auto"></pre></details>';
        (dialog.querySelector(':scope > .dialog-body') || dialog).append(panel);
        panel.querySelector('.update-branch').addEventListener('change', event => {
            selectedBranch = event.target.value; checking = null;
            panel.querySelector('.update-latest').textContent = 'Check the selected version before installing.';
            panel.querySelector('.update-changes').hidden = true;
            message('Selected ' + label(selectedBranch) + '. Check this version to continue.'); buttons();
        });
        panel.querySelector('.update-check').addEventListener('click', check);
        panel.querySelector('.update-install').addEventListener('click', install);
        panel.querySelector('.update-reload').addEventListener('click', () => location.reload());
        api().then(result => { render(result); if (!busy) refreshBranches(); }).catch(error => message(error.message));
    }
    // Footer checks only the installed branch. Installing still uses the existing
    // confirmation, backup/rollback worker and restart flow in this panel.
    window.meshcorestationOpenInstalledUpdate = result => {
        attach(); if (!panel) throw Error('Update settings are not ready.');
        pageBranch=result.branch; selectedBranch=result.branch; render(result);
        const dialog=document.getElementById('companion-dialog');
        if (!dialog.open) dialog.showModal();
        panel.scrollIntoView?.({block:'start'});
    };
    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
    attach();
})();
