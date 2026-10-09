(() => {
    let panel, pending = false, state = {}, timer;
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
        const busy = pending || state.status?.busy;
        panel.querySelector('.firmware-check').disabled = busy;
        panel.querySelector('select').disabled = busy;
        panel.querySelector('.firmware-install').disabled = busy || !state.ready || !panel.querySelector('select').value;
    }
    function render(result) {
        state = result;
        const select = panel.querySelector('select'), previous = select.value;
        select.replaceChildren();
        for (const release of result.releases) {
            const option = document.createElement('option'); option.value = release.id;
            option.textContent = `${release.name}${release.prerelease ? ' (prerelease)' : ''}`; select.append(option);
        }
        if ([...select.options].some(option => option.value === previous)) select.value = previous;
        panel.querySelector('.firmware-current').textContent = `Companion: ${result.device?.ver || 'version unavailable'} · ${result.device?.model || 'model unavailable'} ${result.device?.fw_build || ''}`;
        panel.querySelector('.firmware-message').textContent = result.status?.message || (!result.ready ? 'Update MeshcoreStation dependencies to install esptool before flashing.' : result.releases.length ? 'Select a release to install.' : 'Check for published Heltec V4 OLED USB releases.');
        panel.querySelector('pre').textContent = result.status?.log || '';
        controls();
    }
    async function request(body) {
        if (pending) return;
        pending = true; controls();
        if (body?.action === 'check') panel.querySelector('.firmware-message').textContent = 'Checking GitHub firmware releases…';
        try {
            render(await api(body));
            if (body?.action === 'check' && !state.releases.length) panel.querySelector('.firmware-message').textContent = 'No compatible releases published in zebbel/MeshCore yet. A release needs the Heltec V4 USB manifest and application binary.';
        } catch (error) { if (body?.action === 'install') state.status = {...state.status, busy: true}; panel.querySelector('.firmware-message').textContent = ['TimeoutError', 'AbortError'].includes(error.name) ? 'Firmware request timed out. Try again; check the flashing status before retrying an installation.' : error.message; }
        finally { pending = false; controls(); }
    }
    function attach() {
        const dialog = document.getElementById('companion-dialog');
        if (!dialog || panel) return;
        panel = document.createElement('section'); panel.id = 'firmware-panel'; panel.className = 'companion-section';
        panel.style.gridColumn = '1 / -1';
        panel.innerHTML = '<h3>Companion firmware</h3><p class="firmware-current muted"></p><p>Heltec V4 OLED · USB companion · releases from zebbel/MeshCore. Radio commands pause during installation. Keep USB and power connected.</p><label for="firmware-release">Firmware release</label><select id="firmware-release"></select><div class="companion-toolbar"><button type="button" class="firmware-check">Check firmware releases</button><button type="button" class="firmware-install" disabled>Install firmware</button></div><p class="firmware-message" role="status" aria-live="polite"></p><details><summary>Flashing log</summary><pre style="white-space:pre-wrap;max-height:240px;overflow:auto"></pre></details>';
        dialog.querySelector('.companion-grid').append(panel);
        panel.querySelector('select').addEventListener('change', controls);
        panel.querySelector('.firmware-check').addEventListener('click', () => request({action: 'check'}));
        panel.querySelector('.firmware-install').addEventListener('click', () => {
            const select = panel.querySelector('select');
            if (window.confirm(`Install ${select.selectedOptions[0]?.textContent} on the USB-connected Heltec V4 OLED companion?\n\nConfirm this is the Heltec V4 OLED, not another ESP32 device. Only the application partition is written. No full flash backup is made. Radio service pauses during installation. Keep power connected.`)) {
                request({action: 'install', release_id: Number(select.value), confirm_heltec_v4: true});
            }
        });
        request();
        new MutationObserver(() => { if (dialog.open && !pending) request(); }).observe(dialog, {attributes: true, attributeFilter: ['open']});
        timer = setInterval(() => { if (!pending && state.status?.busy) request(); }, 2500);
    }
    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
    attach();
})();
