(() => {
    let panel, busy = false, checking = null, polling = null;
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
        panel.querySelector('.update-check').disabled = busy;
        panel.querySelector('.update-install').disabled = busy || !checking?.available || !checking?.ready;
    }
    function render(result) {
        checking = result.check || {};
        checking.ready = result.ready;
        panel.querySelector('.update-version').textContent = `Installed: ${result.version} (${result.revision.slice(0, 8)}) · GitHub main`;
        panel.querySelector('.update-latest').textContent = checking.latest ? `Latest checked: ${checking.latest_version} (${checking.latest.slice(0, 8)}) · ${new Date(checking.checked_at * 1000).toLocaleString()}` : 'No update check yet.';
        const link = panel.querySelector('.update-changes');
        link.hidden = !checking.changes_url;
        if (checking.changes_url) link.href = checking.changes_url;
        const state = result.status || {};
        busy = active.has(state.phase);
        message(state.message || (result.ready ? 'Check GitHub for a newer version.' : 'One-time setup needed: run meshcorestation update in the Pi terminal.'));
        panel.querySelector('.update-reload').hidden = state.phase !== 'complete';
        buttons();
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
            await api({action: 'check'});
            render(await api());
            message(checking.available ? (checking.ready ? 'An update is available. Review changes, then install.' : 'Update available. Run meshcorestation update once in the terminal to enable web installation.') : 'You are up to date.');
        } catch (error) { message(error.message); }
        finally { busy = false; buttons(); }
    }
    async function install() {
        if (!checking?.available || !window.confirm(`Install ${checking.latest_version} (${checking.latest.slice(0, 8)}) from GitHub main?\n\nMeshcoreStation will stop briefly. Code, settings, database and dependencies will be backed up. The previous installation will be restored if startup fails.`)) return;
        busy = true; buttons(); message('Submitting update…');
        try { render(await api({action: 'install', target: checking.latest})); startPolling(); }
        catch (error) {
            // A response can be lost when the worker stops the web process. Do not submit twice.
            message(`${error.message} Checking whether the update started…`); startPolling();
        }
    }
    function attach() {
        const dialog = document.getElementById('companion-dialog');
        if (!dialog || panel) return;
        panel = document.createElement('section'); panel.id = 'update-panel'; panel.className = 'companion-section';
        panel.innerHTML = '<h3>Updates</h3><p class="update-version muted"></p><p class="update-latest muted"></p><p>Updates come from zebbel/MeshcoreStation on GitHub. Backups are kept on this Pi.</p><div class="companion-toolbar"><button type="button" class="update-check">Check for updates</button><button type="button" class="update-install" disabled>Install update</button><a class="update-changes" target="_blank" rel="noopener noreferrer" hidden>View changes on GitHub ↗</a><button type="button" class="update-reload" hidden>Reload dashboard</button></div><p class="update-message" role="status" aria-live="polite"></p>';
        dialog.querySelector('.companion-grid').append(panel);
        panel.querySelector('.update-check').addEventListener('click', check);
        panel.querySelector('.update-install').addEventListener('click', install);
        panel.querySelector('.update-reload').addEventListener('click', () => location.reload());
        api().then(render).catch(error => message(error.message));
    }
    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
    attach();
})();
