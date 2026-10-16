(() => {
    let panel, pending = false, actionPending = false, state = {}, timer;
    let releaseKey = null, sourceLoaded = false;
    function setText(node, value) { if (node.textContent !== value) node.textContent = value; }
    function disable(node, value) { if (node.disabled !== Boolean(value)) node.disabled = Boolean(value); }
    async function api(body) {
        const response = await fetch('/api/companion/firmware', {
            method: body ? 'POST' : 'GET', cache: 'no-store',
            headers: {'X-Meshcore-Control': '1', 'Content-Type': 'application/json'},
            ...(body ? {body: JSON.stringify(body)} : {}), signal: AbortSignal.timeout(body?.action === 'check' ? 35000 : 15000)
        });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'Firmware request failed');
        return result;
    }
    function controls() {
        const busy = actionPending || state.status?.busy;
        disable(panel.querySelector('.firmware-check'), busy);
        disable(panel.querySelector('#firmware-source'), busy);
        disable(panel.querySelector('#firmware-release'), busy || !state.supported);
        disable(panel.querySelector('.firmware-install'), busy || !state.ready || (state.source || 'custom') !== panel.querySelector('#firmware-source').value || !panel.querySelector('#firmware-release').value);
    }
    function render(result, refreshDevice = false) {
        state = result;
        if (!sourceLoaded) { panel.querySelector('#firmware-source').value = result.source || 'custom'; sourceLoaded = true; }
        const select = panel.querySelector('#firmware-release'), previous = select.value;
        const nextKey = JSON.stringify([result.source, result.target, result.releases]);
        if (refreshDevice && nextKey !== releaseKey) {
        releaseKey = nextKey;
        select.replaceChildren();
        for (const release of result.releases) {
            const option = document.createElement('option'); option.value = release.id;
            option.textContent = `${release.name}${release.prerelease ? ' (prerelease)' : ''}`; select.append(option);
        }
        if ([...select.options].some(option => option.value === previous)) select.value = previous;
        }
        if (refreshDevice) setText(panel.querySelector('.firmware-current'), `Companion: ${result.device?.ver || 'version unavailable'} · ${result.device?.model || 'model unavailable'} ${result.device?.fw_build || ''}`);
        setText(panel.querySelector('.firmware-message'), result.compatibility_message || result.status?.message || (!result.ready ? 'Update MeshcoreStation dependencies to install esptool before flashing.' : result.releases.length ? 'Select a release to install.' : 'Check for published firmware for ' + (result.target_label || result.device?.model || 'this device') + '.'));
        setText(panel.querySelector('pre'), result.status?.log || '');
        controls();
    }
    async function request(body) {
        if (pending) return;
        pending = true; actionPending = Boolean(body); controls();
        if (body?.action === 'check') panel.querySelector('.firmware-message').textContent = 'Checking GitHub firmware releases…';
        try {
            render(await api(body), body?.action === 'check');
            if (body?.action === 'check' && state.supported && !state.releases.length) panel.querySelector('.firmware-message').textContent = 'No compatible releases found for ' + state.target_label + '. The selected source must provide matching USB companion assets and checksums.';
        } catch (error) { if (body?.action === 'install') state.status = {...state.status, busy: true}; panel.querySelector('.firmware-message').textContent = ['TimeoutError', 'AbortError'].includes(error.name) ? 'Firmware request timed out. Try again; check the flashing status before retrying an installation.' : error.message; }
        finally { pending = false; actionPending = false; controls(); }
    }
    function attach() {
        const dialog = document.getElementById('companion-dialog');
        if (!dialog || panel) return;
        panel = document.createElement('section'); panel.id = 'firmware-panel'; panel.className = 'companion-section';
        panel.style.gridColumn = '1 / -1';
        panel.innerHTML = '<h3>Companion firmware</h3><p class="firmware-current muted">Press Check firmware releases to show the connected device and firmware version.</p><p>Firmware is selected for the connected device from the chosen source. Radio commands pause during installation. Keep USB and power connected.</p><label for="firmware-source">Firmware source</label><select id="firmware-source"><option value="custom">Custom MeshcoreStation (zebbel/MeshCore)</option><option value="official">Official MeshCore (meshcore-dev/MeshCore)</option></select><p class="firmware-source-note muted">Official firmware may not support custom OLED pages or room-server transport. Installation requires a matching partition layout and leaves data partitions untouched.</p><label for="firmware-release">Firmware release</label><select id="firmware-release"></select><div class="companion-toolbar"><button type="button" class="firmware-check">Check firmware releases</button><button type="button" class="firmware-install" disabled>Install firmware</button></div><p class="firmware-message" role="status" aria-live="polite"></p><details><summary>Flashing log</summary><pre style="white-space:pre-wrap;max-height:240px;overflow:auto"></pre></details>';
        dialog.querySelector('.companion-grid').append(panel);
        panel.querySelector('#firmware-release').addEventListener('change', controls);
        panel.querySelector('#firmware-source').addEventListener('change', () => {
            sourceLoaded = true; releaseKey = null;
            panel.querySelector('#firmware-release').replaceChildren();
            panel.querySelector('.firmware-message').textContent = 'Source changed. Press Check firmware releases before installing.';
            controls();
        });
        panel.querySelector('.firmware-check').addEventListener('click', () => request({action: 'check', source: panel.querySelector('#firmware-source').value}));
        panel.querySelector('.firmware-install').addEventListener('click', () => {
            const select = panel.querySelector('#firmware-release');
            if (window.confirm(`Install ${select.selectedOptions[0]?.textContent} on ${state.device?.model || state.target_label}?\n\nSource: ${panel.querySelector('#firmware-source').selectedOptions[0]?.textContent}. Target: ${state.target_label}. Confirm this is the connected device. Only the application partition is written. No full flash backup is made. Radio service pauses during installation. Keep power connected.`)) {
                request({action: 'install', source: panel.querySelector('#firmware-source').value, release_id: Number(select.value), confirm_device: true, target: state.target});
            }
        });
        request();
        timer = setInterval(() => { if (!pending && state.status?.busy) request(); }, 2500);
    }
    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
    attach();
})();
