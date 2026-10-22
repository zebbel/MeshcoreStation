(() => {
    'use strict';
    let panel, busy = false, enabled = null;
    const $ = id => document.getElementById(id);
    async function request(payload) {
        const options = {method: payload ? 'POST' : 'GET', cache: 'no-store',
            headers: {'X-Meshcore-Control': '1'}, signal: AbortSignal.timeout(60000)};
        if (payload) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(payload);
        }
        const res = await fetch('/api/repeater-optimizer/settings', options);
        const data = await res.json();
        if (!res.ok || !data.ok) throw Error(data.error || 'Could not load optimizer settings.');
        return data;
    }
    function render(data) {
        enabled = data.enabled;
        $('optimizer-enabled').checked = enabled;
        $('optimizer-settings-message').textContent = enabled
            ? 'Enabled. Optimizer observations are collected in the background.'
            : 'Disabled. Optimizer data is deleted and collection and scheduled neighbor reads are stopped.';
    }
    async function load() {
        if (busy) return;
        busy = true; $('optimizer-enabled').disabled = true;
        $('optimizer-settings-message').textContent = 'Loading optimizer settings…';
        try { render(await request()); }
        catch (error) { $('optimizer-settings-message').textContent = error.message; }
        finally { busy = false; $('optimizer-enabled').disabled = enabled === null; }
    }
    async function change() {
        const next = $('optimizer-enabled').checked;
        if (busy || enabled === null) return;
        if (!next && !confirm('Disable Repeater Optimizer and delete ALL optimizer data for ALL repeaters? Observations, summaries, neighbors, roles, polling schedules and change history will be deleted. Battery history and general repeater statistics are kept. This cannot be undone.')) {
            $('optimizer-enabled').checked = enabled; return;
        }
        busy = true; $('optimizer-enabled').disabled = true;
        $('optimizer-settings-message').textContent = next ? 'Enabling optimizer…' : 'Disabling optimizer and deleting its data…';
        try {
            render(await request({action: 'enabled', enabled: next, confirm: !next}));
            window.dispatchEvent(new CustomEvent('meshcorestation-optimizer-state'));
        } catch (error) {
            $('optimizer-enabled').checked = enabled;
            $('optimizer-settings-message').textContent = error.message + ' Reload settings to verify the result.';
        } finally { busy = false; $('optimizer-enabled').disabled = false; }
    }
    function attach() {
        if (panel) return;
        const dialog = $('companion-dialog');
        if (!dialog) return;
        panel = document.createElement('section');
        panel.id = 'optimizer-settings'; panel.className = 'companion-section';
        panel.style.marginTop = '20px';
        panel.innerHTML = `<h3>Repeater Optimizer</h3>
            <p class="muted">Analyze observed mesh traffic and review repeater settings. Disabling deletes optimizer data for all repeaters. Enabling starts fresh with manual neighbor polling.</p>
            <label><input id="optimizer-enabled" type="checkbox" disabled> Enable Repeater Optimizer</label>
            <p id="optimizer-settings-message" role="status" aria-live="polite"></p>
            <button id="optimizer-settings-reload" type="button">Reload optimizer settings</button>`;
        (dialog.querySelector('.dialog-body') || dialog).append(panel);
        $('optimizer-enabled').addEventListener('change', change);
        $('optimizer-settings-reload').addEventListener('click', load);
        new MutationObserver(() => { if (dialog.open) load(); }).observe(dialog, {attributes: true, attributeFilter: ['open']});
        if (dialog.open) load();
    }
    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
    attach();
})();
