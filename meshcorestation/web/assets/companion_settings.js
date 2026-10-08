(() => {
    let dialog, settings = null, busy = false, positionMap = null, positionMarker = null;
    let positionDialog = null, currentPositionMarker = null, pickedPosition = null;
    let network = null;
    const groups = {name: ['name'], position: ['adv_lat', 'adv_lon'], tx_power: ['tx_power'], radio: ['radio_freq', 'radio_bw', 'radio_sf', 'radio_cr']};
    const labels = {name: 'Name', adv_lat: 'Latitude', adv_lon: 'Longitude', tx_power: 'Transmit power (dBm)', radio_freq: 'Frequency (MHz)', radio_bw: 'Bandwidth (kHz)', radio_sf: 'Spreading factor', radio_cr: 'Coding rate'};
    const titles = {name: 'Companion name', position: 'Position', tx_power: 'Transmit power', radio: 'Radio parameters'};
    const limits = {adv_lat: [-90, 90, 'any'], adv_lon: [-180, 180, 'any'], tx_power: [0, 255, 1], radio_freq: [150, 2500, 'any'], radio_bw: [7.8, 500, 'any'], radio_sf: [5, 12, 1], radio_cr: [5, 8, 1]};
    const input = key => document.getElementById(`companion-${key}`);
    const status = (message, error = false) => { const box = document.getElementById('companion-message'); box.textContent = message; box.classList.toggle('settings-error', error); };

    function controls() {
        dialog.setAttribute('aria-busy', String(busy));
        // Serial controls remain independently available when the companion is offline.
        dialog.querySelectorAll('input, button').forEach(element => { if (element.closest('#serial-panel, #update-panel, #scope-settings')) return; element.disabled = busy || (!settings && (element.tagName === 'INPUT' || element.type === 'submit')); });
        if (positionMarker) positionMarker.dragging[busy || !settings ? 'disable' : 'enable']();
        networkControls();
    }

    function drafts() {
        return Object.fromEntries(Object.entries(groups).filter(([, keys]) => keys.some(key => input(key).value !== input(key).defaultValue)).map(([group, keys]) => [group, Object.fromEntries(keys.map(key => [key, input(key).value]))]));
    }

    function render(next, keep = {}) {
        settings = next;
        for (const key of Object.values(groups).flat()) { input(key).value = String(next[key]); input(key).defaultValue = String(next[key]); }
        for (const values of Object.values(keep)) for (const [key, value] of Object.entries(values)) input(key).value = value;
        input('tx_power').max = next.max_tx_power;
        document.getElementById('companion-identity').textContent = `${next.name} · ${next.public_key}`;
        document.getElementById('companion-power-limit').textContent = `Device maximum: ${next.max_tx_power} dBm`;
    }

    async function request(payload, url = '/api/companion') {
        const options = {method: payload ? 'POST' : 'GET', headers: {'X-Meshcore-Control': '1'}, cache: 'no-store'};
        if (payload) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(payload); }
        const response = await fetch(url, options);
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'Request failed. Reload settings before retrying.');
        return result;
    }

    async function load() {
        if (busy || ((Object.keys(drafts()).length || networkDirty()) && !window.confirm('Discard unsaved edits and reload the companion settings?'))) return;
        busy = true; settings = null; controls(); status('Reading companion settings… The bot may be finishing a command.');
        try { const result = await request(); render(result.settings); await loadNetwork(); status('Current settings loaded from the companion.'); }
        catch (error) { status(error.message, true); }
        finally { busy = false; controls(); }
    }

    async function save(group, form) {
        if (busy || !settings || !form.reportValidity()) return;
        const values = Object.fromEntries(groups[group].map(key => [key, key === 'name' ? input(key).value : Number(input(key).value)]));
        if (group === 'name' && (!values.name.trim() || new TextEncoder().encode(values.name).length > 31 || /[\x00-\x1f\x7f]/.test(values.name))) { status('Use a name of 1–31 UTF-8 bytes without control characters.', true); return; }
        if (group === 'position' && values.adv_lat === 0 && values.adv_lon === 0) { status('The bot treats 0,0 as a missing position.', true); return; }
        if (groups[group].every(key => values[key] === settings[key])) { status('No changes to save in this section.'); return; }

        const payload = {operation: group, expected: settings};
        if (group === 'name') payload.value = values.name;
        if (group === 'position') payload.value = {latitude: values.adv_lat, longitude: values.adv_lon};
        if (group === 'tx_power') payload.value = values.tx_power;
        if (group === 'radio') {
            const review = groups.radio.map(key => `${labels[key]}: ${settings[key]} → ${values[key]}`).join('\n');
            if (!window.confirm(`Apply these radio settings?\n\n${review}\n\nThe companion may lose contact with your current mesh. Use values supported by your radio and local mesh.`)) return;
            payload.value = {freq: values.radio_freq, bw: values.radio_bw, sf: values.radio_sf, cr: values.radio_cr};
            payload.confirm_radio_change = true;
        }

        const keep = drafts(); delete keep[group];
        busy = true; controls(); status(`Saving ${titles[group].toLowerCase()} and checking the device…`);
        try {
            const result = await request(payload); render(result.settings, keep);
            status(result.warning ? `Device change verified. ${result.warning}` : `${titles[group]} saved and verified.`, Boolean(result.warning));
        } catch (error) {
            settings = null;
            status(`${error.message} Use Reload before another save.`, true);
        } finally { busy = false; controls(); }
    }

    function close() {
        if (!busy && ((!Object.keys(drafts()).length && !networkDirty()) || window.confirm('Close and discard unsaved edits?'))) {
            if (dialog.dispatchEvent(new Event('settings-before-close', {cancelable: true}))) dialog.close();
        }
    }

        function validPosition(lat, lon) {
        if ([lat, lon].some(value => value == null || String(value).trim() === '')) return null;
        lat = Number(lat); lon = Number(lon);
        return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && (lat !== 0 || lon !== 0) ? [lat, lon] : null;
    }

    function syncPositionPicker(center = false) {
        if (!positionMap || !positionDialog.open) return;
        const current = settings && validPosition(settings.adv_lat, settings.adv_lon);
        if (current) {
            if (!currentPositionMarker) currentPositionMarker = L.circleMarker(current, {radius: 22, color: '#087b55', weight: 4, fillColor: '#087b55', fillOpacity: 0.15}).addTo(positionMap).bindTooltip('Current companion position');
            else currentPositionMarker.setLatLng(current);
        } else if (currentPositionMarker) { currentPositionMarker.remove(); currentPositionMarker = null; }

        if (pickedPosition) {
            if (!positionMarker) {
                const icon = L.divIcon({html: '<span class="map-marker bot">B</span>', className: 'map-icon', iconSize: [28, 28], iconAnchor: [14, 14]});
                positionMarker = L.marker(pickedPosition, {icon, draggable: true, title: 'Selected position — drag to move'}).addTo(positionMap);
                positionMarker.on('dragend', event => selectPosition(event.target.getLatLng()));
            } else positionMarker.setLatLng(pickedPosition);
        } else if (positionMarker) { positionMarker.remove(); positionMarker = null; }

        document.getElementById('apply-position-map').disabled = !pickedPosition || busy || !settings;
        document.getElementById('position-map-selection').textContent = pickedPosition ? `Selected: ${pickedPosition.map(value => value.toFixed(6)).join(', ')}` : 'Click the map to select a position.';
        document.getElementById('position-map-current').textContent = current ? `Current: ${current.map(value => value.toFixed(6)).join(', ')}` : 'The companion has no valid current position.';
        positionMap.invalidateSize();
        if (center) {
            const points = [current, pickedPosition].filter(Boolean);
            if (points.length) positionMap.fitBounds(points, {padding: [40, 40], maxZoom: 16});
            else positionMap.setView([51, 10], 5);
        }
    }

    function selectPosition(point) {
        if (busy || !settings) return;
        const wrapped = point.wrap();
        pickedPosition = validPosition(Number(wrapped.lat.toFixed(6)), Number(wrapped.lng.toFixed(6)));
        syncPositionPicker();
    }

    function createPositionPicker() {
        const section = dialog.querySelector('[data-group="position"]');
        const button = document.createElement('button'); button.type = 'button'; button.className = 'info-button'; button.textContent = 'Choose on map';
        section.insertBefore(button, section.querySelector('.companion-fields'));

        positionDialog = document.createElement('dialog'); positionDialog.id = 'position-map-dialog'; positionDialog.setAttribute('aria-labelledby', 'position-map-title');
        positionDialog.innerHTML = '<div class="dialog-header"><h2 id="position-map-title">Choose companion position</h2><button type="button" id="close-position-map" aria-label="Close position map">×</button></div><p class="muted">Green ring = current companion position. Orange B = selected position. Click or drag to select; scroll to zoom.</p><p id="position-map-current" class="muted"></p><div id="companion-position-map" class="map-canvas" role="region" aria-label="Companion position picker"></div><p id="position-map-selection" role="status" aria-live="polite"></p><p id="position-map-error" class="muted"></p><div class="position-map-actions"><button type="button" id="cancel-position-map">Cancel</button><button type="button" id="apply-position-map" class="info-button">Apply</button></div>';
        window.meshcorestationPrepareDialog(positionDialog);
        document.body.append(positionDialog);

        button.addEventListener('click', () => {
            if (busy || !settings) { status('Load companion settings first.', true); return; }
            if (!positionMap) { status('Map library unavailable. Refresh the page or enter coordinates manually.', true); return; }
            pickedPosition = validPosition(input('adv_lat').value, input('adv_lon').value) || validPosition(settings.adv_lat, settings.adv_lon);
            positionDialog.showModal();
            syncPositionPicker(true);
        });

        document.getElementById('close-position-map').addEventListener('click', () => positionDialog.close());
        document.getElementById('cancel-position-map').addEventListener('click', () => positionDialog.close());
        document.getElementById('apply-position-map').addEventListener('click', () => {
            if (!pickedPosition || busy || !settings) return;
            input('adv_lat').value = pickedPosition[0].toFixed(6); input('adv_lon').value = pickedPosition[1].toFixed(6);
            positionDialog.close();
            status('Position applied to the fields. Click Save position to update the companion.');
        });

        if (!window.L) return;
        positionMap = L.map('companion-position-map', {scrollWheelZoom: true, worldCopyJump: true}).setView([51, 10], 5);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, noWrap: true, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'}).on('tileerror', () => { document.getElementById('position-map-error').textContent = 'Background tiles unavailable. Check your Internet connection or use the coordinate fields.'; }).addTo(positionMap);
        positionMap.on('click', event => selectPosition(event.latlng));
        new ResizeObserver(() => { if (positionDialog.open) positionMap.invalidateSize(); }).observe(document.getElementById('companion-position-map'));
    }

    const networkInput = key => document.getElementById(`network-${key}`);

    function networkMessage(message, error = false) {
        const box = document.getElementById('network-message'); box.textContent = message; box.classList.toggle('settings-error', error);
    }

    function networkDirty() {
        return network && ['path_hash_size', 'default_scope'].some(key => networkInput(key).value !== networkInput(key).dataset.loaded);
    }

    function networkControls() {
        if (!document.getElementById('network-settings')) return;
        for (const key of ['path_hash_size', 'default_scope']) {
            const disabled = busy || !settings || !network || network[key] === null;
            networkInput(key).disabled = disabled;
            document.getElementById(`save-network-${key}`).disabled = disabled;
        }
    }

    function renderNetwork(next, keep = {}) {
        if (!settings || next.public_key !== settings.public_key) throw new Error('Companion identity changed. Reload settings.');
        network = next;
        for (const key of ['path_hash_size', 'default_scope']) {
            const value = key === 'path_hash_size' ? String(next[key] ?? '') : next[key]?.name ?? '';
            networkInput(key).value = value; networkInput(key).dataset.loaded = value;
            if (key in keep) networkInput(key).value = keep[key];
        }
        document.getElementById('network-current').textContent = `Current: ${next.path_hash_size === null ? 'path hash unavailable' : next.path_hash_size + ' bytes per hop'} · ${next.default_scope === null ? 'scope unavailable' : next.default_scope.name || 'Unscoped'}`;
    }

    async function loadNetwork() {
        network = null; networkControls(); networkMessage('Reading network settings…');
        try {
            const result = await request(undefined, '/api/companion/network'); renderNetwork(result.network);
            networkMessage(result.warnings?.length ? result.warnings.join(' ') : 'Network settings loaded.', Boolean(result.warnings?.length));
        } catch (error) { network = null; networkMessage(error.message, true); }
    }

    async function saveNetwork(operation) {
        if (busy || !settings || !network || network[operation] === null) return;
        let value = networkInput(operation).value;
        if (operation === 'path_hash_size') value = Number(value);
        else {
            value = value.trim();
            if (value) {
                value = value.replace(/^#/, '');
                if (!/^[A-Za-z0-9_-]{1,29}$/.test(value)) { networkMessage('Use 1–29 letters, digits, hyphens or underscores for the region.', true); return; }
            }
        }

        const current = operation === 'path_hash_size' ? network.path_hash_size : network.default_scope.name;
        if (value === current) { networkMessage('No changes to save.'); return; }
        const label = operation === 'path_hash_size' ? 'Default path hash size (bytes)' : 'Default region scope';
        if (!window.confirm(`${label}: ${current || 'Unscoped'} → ${value || 'Unscoped'}\n\nApply this change to the companion?`)) return;

        const keep = {};
        for (const key of ['path_hash_size', 'default_scope']) if (key !== operation && networkInput(key).value !== networkInput(key).dataset.loaded) keep[key] = networkInput(key).value;

        busy = true; controls(); networkMessage('Saving and verifying network settings…');
        try {
            const result = await request({operation, value, expected: network, confirm_network_change: true}, '/api/companion/network');
            renderNetwork(result.network, keep);
            networkMessage(result.warnings?.length ? `Change verified. ${result.warnings.join(' ')}` : `${label} saved and verified.`, Boolean(result.warnings?.length));
        } catch (error) { network = null; networkMessage(`${error.message} Use Reload before another network save.`, true); }
        finally { busy = false; controls(); }
    }

    function createNetworkSettings() {
        const section = document.createElement('section'); section.id = 'network-settings'; section.className = 'companion-section';
        section.innerHTML = '<h3>Network settings</h3><p id="network-current" class="muted">Waiting for the companion</p><div class="companion-fields"><div><label for="network-path_hash_size">Default path hash size</label><select id="network-path_hash_size"><option value="" disabled>Unavailable</option><option value="1">1 byte per hop</option><option value="2">2 bytes per hop</option><option value="3">3 bytes per hop</option></select><button type="button" id="save-network-path_hash_size" class="info-button">Save path hash size</button></div><div><label for="network-default_scope">Default region scope</label><input id="network-default_scope" type="text" maxlength="30" placeholder="Unscoped" autocomplete="off"><p class="muted">Enter a region name. Leave empty for Unscoped.</p><button type="button" id="save-network-default_scope" class="info-button">Save default scope</button></div></div><p id="network-message" role="status" aria-live="polite"></p>';
        dialog.querySelector('.companion-grid').append(section);
        for (const key of ['path_hash_size', 'default_scope']) document.getElementById(`save-network-${key}`).addEventListener('click', () => saveNetwork(key));
    }

    function create() {
        dialog = document.createElement('dialog'); dialog.id = 'companion-dialog'; dialog.setAttribute('aria-labelledby', 'companion-title');
        const sections = Object.entries(groups).map(([group, keys]) => {
            const fields = keys.map(key => {
                const attributes = key === 'name' ? 'type="text" maxlength="31"' : `type="number" min="${limits[key][0]}" max="${limits[key][1]}" step="${limits[key][2]}"`;
                return `<label for="companion-${key}">${labels[key]}<input id="companion-${key}" ${attributes} required autocomplete="off"></label>`;
            }).join('');
            const note = group === 'radio' ? 'Changing these values may disconnect the companion from your current mesh.' : group === 'position' ? 'Updates the companion and its saved bot position.' : group === 'tx_power' ? 'Device maximum: —' : 'Maximum 31 UTF-8 bytes.';
            return `<form class="companion-section" data-group="${group}"><h3>${titles[group]}</h3><p class="muted" ${group === 'tx_power' ? 'id="companion-power-limit"' : ''}>${note}</p><div class="companion-fields">${fields}</div><button type="submit" class="info-button">Save ${group === 'radio' ? 'radio settings…' : titles[group].toLowerCase()}</button></form>`;
        }).join('');

        dialog.innerHTML = `<div class="dialog-header"><h2 id="companion-title">Companion settings</h2><button type="button" id="close-companion" aria-label="Close companion settings">×</button></div><section id="serial-panel" class="companion-section serial-panel" aria-label="Serial port settings"></section><p id="companion-identity" class="muted">Connected through your bot</p><div class="companion-toolbar"><button type="button" id="reload-companion">Reload</button><span class="muted">Each section is saved separately.</span></div><p id="companion-message" role="status" aria-live="polite"></p><div class="companion-grid">${sections}</div>`;
        window.meshcorestationPrepareDialog(dialog);
        document.body.append(dialog);
        createPositionPicker();
        createNetworkSettings();
        dialog.addEventListener('submit', event => { if (!event.target.dataset.group) return; event.preventDefault(); save(event.target.dataset.group, event.target); });
        dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
        document.getElementById('close-companion').addEventListener('click', close);
        document.getElementById('reload-companion').addEventListener('click', load);
    }

    document.addEventListener('click', event => {
        if (!event.target.closest('#open-companion')) return;
        if (!dialog) create();
        if (dialog.open) return;
        settings = null; network = null;
        dialog.querySelectorAll('input').forEach(element => { if(element.closest('#scope-settings'))return; element.value = ''; element.defaultValue = ''; });
        dialog.showModal(); load();
    });
})();