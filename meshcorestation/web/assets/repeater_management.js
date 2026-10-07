/* Remote repeater management. Secrets and session tokens live only in this page. */
(() => {
    let loginDialog, dialog, contact, session = '', admin = false, busy = false, schema = {}, selectedTab = 'status';
    const values = new Map(), inputs = new Map(), loaded = new Set();
    const $ = id => document.getElementById(id);
    function node(tag, text, cls) { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; if (cls) item.className = cls; return item; }
    function button(text, handler, cls) { const item = node('button', text, cls); item.type = 'button'; item.addEventListener('click', handler); return item; }
    function message(text, error = false) { const box = $('repeater-message'); box.textContent = text; box.classList.toggle('repeater-error', error); }
    function controls() {
        for (const root of [dialog, loginDialog]) if (root) {
            root.setAttribute('aria-busy', String(busy));
            root.querySelectorAll('button,input,select,textarea').forEach(item => { item.disabled = busy || item.dataset.unavailable === 'true' || (item.closest('#repeater-config') && !admin); });
        }
        inputs.forEach((input, field) => { input.disabled = busy || !admin || (schema[field].kind !== 'password' && !values.has(field)); });
        if ($('repeater-choose-map')) $('repeater-choose-map').disabled = !canPickLocation();
    }
    async function request(payload) {
        const response = await fetch('/api/repeater', {method: 'POST', cache: 'no-store', headers: {'Content-Type': 'application/json', 'X-Meshcore-Control': '1'}, body: JSON.stringify({...payload, public_key: contact.public_key, session})});
        let result;
        try { result = await response.json(); } catch { throw new Error('Unreadable response. A submitted change may have applied; read before retrying.'); }
        if (result.expired) { session = ''; admin = false; $('repeater-reconnect').hidden = false; }
        if (!response.ok || !result.ok) throw new Error(result.error || 'Repeater request failed.');
        if (typeof result.admin === 'boolean') admin = result.admin;
        return result;
    }
    async function run(work, report = message) {
        if (busy) return;
        busy = true; controls();
        try { await work(); } catch (error) { report(error.message, true); }
        finally { busy = false; controls(); }
    }
    function dirty() { return [...inputs].some(([field, input]) => schema[field].kind === 'password' ? input.value !== '' : values.has(field) && input.value !== values.get(field)); }
    function forget() {
        if (session) {
            // Retire the server token on close; no remote logout that would disturb monitoring.
            fetch('/api/repeater', {method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json', 'X-Meshcore-Control': '1'}, body: JSON.stringify({action: 'logout', public_key: contact.public_key, session})}).catch(() => {});
        }
        session = ''; inputs.forEach(input => { if (input.type === 'password') input.value = ''; });
    }
    function close() {
        if (busy || (dirty() && !window.confirm('Discard unsaved repeater edits?'))) return;
        forget(); dialog.close();
    }
    function tab(name) {
        selectedTab = name;
        for (const value of ['status', 'config']) {
            const active = value === name;
            $('repeater-tab-' + value).setAttribute('aria-selected', String(active));
            $('repeater-tab-' + value).tabIndex = active ? 0 : -1;
            $('repeater-' + value).hidden = !active;
        }
    }
    function create() {
        dialog = node('dialog'); dialog.id = 'repeater-manage-dialog'; dialog.setAttribute('aria-labelledby', 'repeater-title');
        dialog.innerHTML = `<div class="dialog-header"><h2 id="repeater-title">Repeater management</h2><button type="button" id="repeater-close" aria-label="Close repeater management">×</button></div>
            <div class="repeater-fixed"><strong id="repeater-name"></strong><p id="repeater-identity" class="muted"></p><div class="repeater-tabs" role="tablist" aria-label="Repeater management">
            <button type="button" id="repeater-tab-status" role="tab" aria-controls="repeater-status">Status</button><button type="button" id="repeater-tab-config" role="tab" aria-controls="repeater-config">Configurations</button></div></div>
            <div class="dialog-body"><p id="repeater-message" role="status" aria-live="polite"></p><button type="button" id="repeater-reconnect" hidden>Connect again</button>
            <section id="repeater-status" role="tabpanel" aria-labelledby="repeater-tab-status"><div class="repeater-toolbar"><span id="repeater-last-response" class="muted">Not yet read</span><button type="button" id="repeater-refresh">↻ Refresh</button></div><div id="repeater-status-cards"></div><div id="repeater-extras"></div></section>
            <section id="repeater-config" role="tabpanel" aria-labelledby="repeater-tab-config" hidden></section></div>`;
        document.body.append(dialog);
        $('repeater-close').addEventListener('click', close);
        dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
        $('repeater-refresh').addEventListener('click', () => run(readStatus));
        $('repeater-reconnect').addEventListener('click', () => { if (dirty() && !window.confirm('Discard unsaved edits and reconnect?')) return; forget(); dialog.close(); openLogin(); });
        for (const name of ['status', 'config']) $('repeater-tab-' + name).addEventListener('click', () => tab(name));
        dialog.querySelector('[role="tablist"]').addEventListener('keydown', event => {
            if (busy || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault(); tab(event.key === 'Home' ? 'status' : event.key === 'End' ? 'config' : selectedTab === 'status' ? 'config' : 'status'); $('repeater-tab-' + selectedTab).focus();
        });
        loginDialog = node('dialog'); loginDialog.id = 'repeater-login-dialog'; loginDialog.setAttribute('aria-labelledby', 'repeater-login-title');
        loginDialog.innerHTML = `<div class="dialog-header"><h2 id="repeater-login-title">Connect to repeater</h2><button type="button" id="repeater-login-close" aria-label="Close repeater login">×</button></div><div class="dialog-body"><p id="repeater-login-name"></p><form id="repeater-login-form"><label for="repeater-password">Admin password</label><div class="repeater-password"><input id="repeater-password" type="password" autocomplete="off"><button type="button" id="repeater-show-password" aria-label="Show password">Show</button></div><p class="muted">Leave blank to use existing permissions or guest access. Passwords are not saved.</p><p id="repeater-login-message" role="status" aria-live="polite"></p><button type="submit">Connect</button></form></div>`;
        document.body.append(loginDialog);
        const closeLogin = () => { if (!busy) { $('repeater-password').value = ''; loginDialog.close(); } };
        $('repeater-login-close').addEventListener('click', closeLogin);
        loginDialog.addEventListener('cancel', event => { event.preventDefault(); closeLogin(); });
        $('repeater-show-password').addEventListener('click', () => { const input = $('repeater-password'), show = input.type === 'password'; input.type = show ? 'text' : 'password'; $('repeater-show-password').textContent = show ? 'Hide' : 'Show'; });
        $('repeater-login-form').addEventListener('submit', async event => {
            event.preventDefault(); if (busy) return;
            busy = true; controls(); $('repeater-login-message').textContent = 'Connecting… This can take up to 40 seconds.';
            const password = $('repeater-password').value; $('repeater-password').value = '';
            try {
                const result = await request({action: 'login', password});
                session = result.session; admin = result.admin; schema = result.fields;
                values.clear(); inputs.clear(); loaded.clear(); buildConfig(); buildExtras();
                $('repeater-name').textContent = contact.name || '(unnamed repeater)';
                identity(result.contact); $('repeater-reconnect').hidden = true;
                $('repeater-status-cards').replaceChildren(); $('repeater-last-response').textContent = 'Not yet read';
                loginDialog.close(); tab('status'); dialog.showModal();
                await readStatus();
            } catch (error) {
                if (dialog.open) message(error.message, true); else $('repeater-login-message').textContent = error.message;
            } finally { busy = false; controls(); }
        });
    }
    function identity(info) {
        const hops = info.out_path_len;
        $('repeater-identity').textContent = contact.public_key.slice(0, 12) + '… · ' + (hops === 0 ? 'Direct' : hops > 0 ? hops + ' hops' : 'Flood route') + (admin ? '' : ' · Guest access');
        $('repeater-identity').title = contact.public_key;
    }
    function openLogin() {
        $('repeater-login-name').textContent = contact.name || contact.public_key;
        $('repeater-login-message').textContent = ''; $('repeater-password').value = ''; $('repeater-password').type = 'password'; $('repeater-show-password').textContent = 'Show';
        controls(); loginDialog.showModal(); $('repeater-password').focus();
    }
    window.meshcorestationManageRepeater = selected => {
        if (busy || selected.type !== 2) return;
        if (!dialog) create();
        if (dialog.open || loginDialog.open) return;
        contact = {...selected}; session = ''; admin = false; openLogin();
    };
    const duration = value => { if (!Number.isFinite(value)) return 'Not available'; const seconds = Math.max(0, Math.floor(value)); return `${Math.floor(seconds / 86400)}d ${Math.floor(seconds / 3600) % 24}h ${Math.floor(seconds / 60) % 60}m`; };
    const unit = (value, suffix = '') => Number.isFinite(value) ? value + suffix : 'Not available';
    function card(title, rows) {
        const section = node('section', undefined, 'repeater-section'), list = node('dl'); section.append(node('h3', title));
        for (const [label, value] of rows) list.append(node('dt', label), node('dd', value));
        section.append(list); return section;
    }
    async function readStatus() {
        message('Reading repeater status…');
        const result = await request({action: 'status'}), data = result.data, cards = $('repeater-status-cards');
        identity(result.contact);
        cards.replaceChildren(card('System', [['Battery', Number.isFinite(data.bat) ? window.MeshcoreStationBattery.reading(data.bat / 1000) : 'Not available'], ['Uptime', duration(data.uptime)], ['Queue', unit(data.tx_queue_len)], ['Firmware level', unit(result.firmware_level)], ['Debug events', unit(data.full_evts)]]),
            card('Radio', [['Last RSSI', unit(data.last_rssi, ' dBm')], ['Last SNR', unit(data.last_snr, ' dB')], ['Noise floor', unit(data.noise_floor, ' dBm')], ['TX airtime', duration(data.airtime)], ['RX airtime', duration(data.rx_airtime)], ['Receive errors', unit(data.recv_errors)]]));
        const packet = node('section', undefined, 'repeater-section'); packet.append(node('h3', 'Packets'));
        packet.append(table(['Type', 'Sent', 'Received'], [['Flood', unit(data.sent_flood), unit(data.recv_flood)], ['Direct', unit(data.sent_direct), unit(data.recv_direct)], ['Total', unit(data.nb_sent), unit(data.nb_recv)]]));
        packet.append(node('p', 'Duplicates · Flood: ' + unit(data.flood_dups) + ' · Direct: ' + unit(data.direct_dups), 'muted')); cards.append(packet);
        $('repeater-last-response').textContent = 'Last response: ' + new Date(result.sampled_at * 1000).toLocaleString(undefined, {timeZone: 'Europe/Berlin'}) + ' · Europe/Berlin';
        message(admin ? 'Status received.' : 'Guest session: status is available; configurations require administrator access.');
    }
    function table(headings, rows) {
        const grid = node('table'), head = node('thead'), tr = node('tr'), body = node('tbody');
        headings.forEach(label => tr.append(node('th', label))); head.append(tr);
        rows.forEach(row => { const line = node('tr'); row.forEach(value => line.append(node('td', typeof value === 'object' ? JSON.stringify(value) : String(value ?? 'Not available')))); body.append(line); });
        grid.append(head, body); return grid;
    }
    function disclosure(title, subtitle) {
        const details = node('details', undefined, 'repeater-section'), summary = node('summary'); summary.append(node('strong', title));
        if (subtitle) summary.append(node('small', subtitle, 'muted')); details.append(summary); return details;
    }
    function buildExtras() {
        const root = $('repeater-extras'); root.replaceChildren();
        for (const [action, label] of [['telemetry', 'Telemetry'], ['neighbors', 'Neighbors']]) {
            const box = disclosure(label), content = node('div', undefined, 'repeater-extra-content');
            const localMessage = node('p', '', 'muted');
            localMessage.setAttribute('role', 'status'); localMessage.setAttribute('aria-live', 'polite');
            if (action === 'neighbors') localMessage.id = 'repeater-neighbors-message';
            const report = action === 'neighbors' ? (text, error = false) => { localMessage.textContent = text; localMessage.classList.toggle('repeater-error', error); } : message;
            let offset = 0;
            const load = async (more = false) => {
                report('Reading ' + label.toLowerCase() + '…');
                const result = await request({action, offset: more ? offset : 0});
                if (!more) content.replaceChildren();
                if (action === 'neighbors') {
                    const data = result.data, rows = data.neighbours || [];
                    content.append(table(['Repeater', 'Last heard', 'SNR'], rows.map(row => [row.name || row.pubkey, duration(row.secs_ago) + ' ago', unit(row.snr, ' dB')])));
                    offset = (more ? offset : 0) + rows.length;
                    next.hidden = offset >= data.neighbours_count || rows.length === 0;
                    content.append(node('p', `${offset} / ${data.neighbours_count} neighbors`, 'muted'));
                } else {
                    if (Array.isArray(result.data)) content.append(result.data.length ? table(['Channel', 'Sensor', 'Value'], result.data.map(row => [row.channel, row.type, Number.isFinite(row.value) && row.type === 'voltage' ? row.value.toFixed(2) + ' V' : Number.isFinite(row.value) && row.type === 'temperature' ? row.value.toFixed(1) + ' °C' : row.value])) : node('p', 'The repeater returned no sensor readings.'));
                    else content.append(node('pre', JSON.stringify(result.data, null, 2), 'repeater-data'));
                }
                loaded.add(action); report(label + ' received.');
            };
            const refresh = button('↻ Refresh', () => run(() => load(), report)), next = button('Load more', () => run(() => load(true), report)); next.hidden = true;
            box.append(refresh); if (action === 'neighbors') box.append(localMessage); box.append(content); if (action === 'neighbors') box.append(next);
            box.addEventListener('toggle', () => { if (box.open && !loaded.has(action) && !busy) run(() => load(), report); }); root.append(box);
        }
    }
    function fieldValue(field) {
        const input = inputs.get(field);
        if (schema[field].kind === 'radio') return [...input.querySelectorAll('input')].map(item => item.value).join(',');
        return input.value;
    }
    function setValue(field, value) {
        const input = inputs.get(field); values.set(field, value);
        if (schema[field].kind === 'radio') {
            const parts = value.split(','); input.querySelectorAll('input').forEach((item, i) => { item.value = parts[i] || ''; });
        } else input.value = schema[field].kind === 'textarea' ? value.replaceAll('|', '\n') : value;
        // Keep comparisons in the same representation the user edits.
        values.set(field, fieldValue(field));
    }
    function makeField(field, spec) {
        const label = node(spec.kind === 'radio' ? 'div' : 'label', spec.label, 'repeater-field'); let input;
        if (spec.kind === 'radio') {
            input = node('fieldset', undefined, 'repeater-radio-fields'); input.append(node('legend', 'Radio parameters'));
            for (const [name, placeholder] of [['Frequency (MHz)', '868.000'], ['Bandwidth (kHz)', '62.5'], ['Spreading factor', '7'], ['Coding rate', '5']]) {
                const part = node('label', name), entry = node('input'); entry.type = 'number'; entry.step = 'any'; entry.placeholder = placeholder; entry.setAttribute('aria-label', name); part.append(entry); input.append(part);
            }
            // A value property lets shared dirty-state handling treat this group as one field.
            Object.defineProperty(input, 'value', {get: () => [...input.querySelectorAll('input')].map(i => i.value).join(',')});
        } else if (spec.kind === 'select') {
            input = node('select'); spec.options.forEach((value, i) => { const option = node('option', spec.labels?.[i] || value); option.value = value; input.append(option); });
        } else {
            input = node(spec.kind === 'textarea' ? 'textarea' : 'input');
            if (input.tagName === 'INPUT') input.type = spec.kind === 'password' ? 'password' : spec.kind === 'number' ? 'number' : 'text';
            if (spec.kind === 'number') { input.min = spec.low; input.max = spec.high; input.step = spec.step || 'any'; }
            if (spec.kind === 'password') { input.autocomplete = 'new-password'; input.placeholder = 'Leave blank to keep unchanged'; }
        }
        input.id = 'repeater-field-' + field.replaceAll('.', '-'); input.setAttribute('aria-label', spec.label); inputs.set(field, input);
        label.append(input); const hint = node('small', spec.kind === 'password' ? 'Write-only; not saved in MeshcoreStation.' : 'Read this section to load the current value.', 'muted'); hint.id = input.id + '-hint'; label.append(hint);
        return label;
    }
    const sections = [['basic', 'Basic settings', ''], ['radio', 'Radio', 'Frequency, bandwidth, SF, CR, TX power'], ['location', 'Location', 'Latitude and longitude'], ['advertisements', 'Advertisements', 'Local and flood intervals'], ['routing', 'Routing and regions', 'Forwarding, hop limits and regions'], ['access', 'Access', 'Guest access and permissions'], ['owner', 'Owner information', ''], ['advanced', 'Advanced', '']];
    function canPickLocation() { return !busy && admin && !!session && values.has('lat') && values.has('lon'); }
    function buildConfig() {
        const root = $('repeater-config'); root.replaceChildren();
        for (const [section, title, subtitle] of sections) {
            const box = disclosure(title, subtitle); box.open = section === 'basic';
            const form = node('form'), fields = Object.keys(schema).filter(field => schema[field].section === section), grid = node('div', undefined, 'repeater-fields');
            fields.forEach(field => grid.append(makeField(field, schema[field]))); form.append(grid);
            const toolbar = node('div', undefined, 'repeater-toolbar');
            toolbar.append(button('Read', () => run(() => readSection(fields)))); const save = node('button', 'Save section'); save.type = 'submit'; toolbar.append(save); form.append(toolbar);
            form.addEventListener('submit', event => { event.preventDefault(); if (form.reportValidity()) run(() => saveSection(fields)); });
            box.append(form);
            if (section === 'location') {
                const choose = button('Choose on map', () => {
                    if (!canPickLocation()) return;
                    window.MeshcoreStationRepeaterLocation.open({current: [values.get('lat'), values.get('lon')], draft: [inputs.get('lat').value, inputs.get('lon').value], canEdit: canPickLocation,
                        report: message, apply: point => { inputs.get('lat').value = point[0].toFixed(6); inputs.get('lon').value = point[1].toFixed(6); message('Position applied to the fields. Click Save section to update the repeater.'); }});
                });
                choose.id = 'repeater-choose-map'; form.insertBefore(choose, grid);
            }
            if (section === 'routing') buildRegions(box);
            if (section === 'access') buildPermissions(box);
            root.append(box);
        }
        const actions = node('section', undefined, 'repeater-section'); actions.append(node('h3', 'Actions'));
        const toolbar = node('div', undefined, 'repeater-action-buttons');
        for (const [name, title] of [['advert', 'Send advert'], ['clock_sync', 'Sync clock'], ['reboot', 'Reboot repeater']]) toolbar.append(button(title, () => {
            if (!window.confirm(`${title} on ${contact.name}?`)) return;
            run(async () => { message(title + '…'); const result = await request({action: 'action', name, confirm: true}); message(result.message); });
        }, name === 'reboot' ? 'repeater-danger' : ''));
        actions.append(toolbar); root.append(actions, node('p', 'Available settings depend on firmware. Read values before editing. Sections are saved separately.', 'muted'));
    }
    async function readSection(fields) {
        if (fields.some(field => schema[field].kind !== 'password' && values.has(field) && fieldValue(field) !== values.get(field)) && !window.confirm('Discard unsaved edits in this section and read current values?')) return;
        const failures = [];
        for (const field of fields) {
            if (schema[field].kind === 'password') continue;
            message('Reading ' + schema[field].label + '…');
            try {
                const result = await request({action: 'read', field}); setValue(field, result.value);
                $(inputs.get(field).id + '-hint').textContent = 'Read from repeater.';
            } catch (error) { values.delete(field); $(inputs.get(field).id + '-hint').textContent = error.message; failures.push(schema[field].label + ': ' + error.message); if (!session || /timed out|timeout|two minutes|Administrator/i.test(error.message)) break; }
        }
        message(failures.length ? failures.join('\n') : 'Section read from repeater.', failures.length > 0);
    }
    async function saveSection(fields) {
        const changed = fields.filter(field => schema[field].kind === 'password' ? fieldValue(field) !== '' : values.has(field) && fieldValue(field) !== values.get(field));
        if (!changed.length) { message('No changes to save.'); return; }
        const review = changed.map(field => schema[field].label + ': ' + (schema[field].kind === 'password' ? '(new password)' : fieldValue(field))).join('\n');
        if (!window.confirm(`Save to ${contact.name}?\n\n${review}${changed.includes('radio') ? '\n\nRadio changes may require a reboot and can affect connectivity.' : ''}`)) return;
        const saved = []; let reboot = false;
        for (const field of changed) {
            message('Saving ' + schema[field].label + '…');
            const value = fieldValue(field), expected = values.get(field);
            // Do not keep a submitted password in the form, including on failure.
            if (schema[field].kind === 'password') inputs.get(field).value = '';
            try {
                const result = await request({action: 'write', field, value, expected: schema[field].kind === 'textarea' ? expected?.replaceAll('\n', '|') : expected, confirm: true});
                if (schema[field].kind !== 'password') setValue(field, result.value);
                saved.push(schema[field].label); reboot ||= result.reboot_required;
                $(inputs.get(field).id + '-hint').textContent = result.message;
            } catch (error) {
                if (schema[field].kind !== 'password') values.delete(field);
                message(`${saved.length ? 'Confirmed: ' + saved.join(', ') + '. ' : ''}${schema[field].label}: ${error.message} Remaining fields were not sent. Read this section before retrying.`, true); return;
            }
        }
        message('Confirmed: ' + saved.join(', ') + '.' + (reboot ? ' Reboot required to apply radio settings.' : ''));
    }
    function buildRegions(box) {
        const section = node('div', undefined, 'repeater-subsection'), output = node('pre', 'Regions have not been read.', 'repeater-data');
        section.append(node('h4', 'Regions'), button('Read regions', () => run(async () => { const result = await request({action: 'regions_read'}); output.textContent = result.data; message('Region response received.'); })), output);
        const form = node('form'), name = node('input'), parent = node('input'), operation = node('select');
        name.placeholder = 'Region name, e.g. #Europe'; name.required = true; name.setAttribute('aria-label', 'Region name'); parent.placeholder = 'Parent region (default *)'; parent.setAttribute('aria-label', 'Parent region');
        for (const [value, label] of [['put', 'Add / update parent'], ['remove', 'Remove'], ['allowf', 'Allow flooding'], ['denyf', 'Block flooding'], ['home', 'Set home'], ['default', 'Set default scope']]) { const option = node('option', label); option.value = value; operation.append(option); }
        operation.setAttribute('aria-label', 'Region operation'); form.append(name, parent, operation); const apply = node('button', 'Apply region change'); apply.type = 'submit'; form.append(apply);
        form.addEventListener('submit', event => { event.preventDefault(); if (!form.reportValidity() || !window.confirm(`${operation.selectedOptions[0].textContent}: ${name.value} on ${contact.name}?`)) return; run(async () => { const result = await request({action: 'region', verb: operation.value, name: name.value, parent: parent.value, confirm: true}); message(result.message); }); });
        section.append(form, node('p', 'These are the repeater’s forwarding regions. Names, including any # prefix, are sent exactly as entered. Long region lists may be truncated by firmware.', 'muted')); box.append(section);
    }
    function buildPermissions(box) {
        const section = node('div', undefined, 'repeater-subsection'), output = node('div'); section.append(node('h4', 'Companion permissions'));
        section.append(button('Read permissions', () => run(async () => { const result = await request({action: 'acl'}); output.replaceChildren(table(['Public key prefix', 'Permission'], result.data.map(row => [row.key, row.perm]))); message('Permissions received.'); })), output);
        const form = node('form'), key = node('input'), permission = node('select'); key.placeholder = 'Full companion public key'; key.pattern = '[a-fA-F0-9]{64}'; key.required = true; key.setAttribute('aria-label', 'Companion public key');
        ['Guest (0)', 'Read-only (1)', 'Read-write (2)', 'Admin (3)'].forEach((text, i) => { const option = node('option', text); option.value = String(i); permission.append(option); }); permission.setAttribute('aria-label', 'Permission');
        const save = node('button', 'Apply permission'); save.type = 'submit'; form.append(key, permission, save);
        form.addEventListener('submit', event => { event.preventDefault(); if (!form.reportValidity() || !window.confirm(`Set ${permission.selectedOptions[0].textContent} for ${key.value}? Changing your companion’s permission may end management access.`)) return; run(async () => { const result = await request({action: 'permission', target: key.value, permission: permission.value, confirm: true}); message(result.message); }); });
        section.append(form); box.append(section);
    }
})();
