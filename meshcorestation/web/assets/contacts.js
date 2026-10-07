(() => {
    let dialog, snapshot = null, busy = false;
    const byId = id => document.getElementById(id);
    const types = {1: ['📱', 'Companion'], 2: ['📡', 'Repeater'], 3: ['💬', 'Room'], 4: ['🌡️', 'Sensor']};

    function message(text, error = false) {
        byId('contacts-message').textContent = text;
        byId('contacts-message').classList.toggle('contacts-error', error);
    }

    function controls() {
        dialog.querySelectorAll('button, input, select').forEach(element => {
            element.disabled = busy || (!snapshot && element.closest('#contact-form, #contacts-list'));
        });
        byId('contacts-add').disabled = busy || !snapshot;
        dialog.setAttribute('aria-busy', String(busy));
    }

    function dirty() {
        return ['contact-name', 'contact-key', 'contact-lat', 'contact-lon'].some(id => byId(id).value !== '') || byId('contact-type').value !== '1';
    }

    function close() {
        if (!busy && (!dirty() || window.confirm('Discard the unfinished contact?'))) dialog.close();
    }

    async function request(payload) {
        const options = {cache: 'no-store', headers: {'X-Meshcore-Control': '1'}};
        if (payload) {
            options.method = 'POST'; options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(payload);
        }
        const response = await fetch('/api/companion/contacts', options);
        let result;
        try { result = await response.json(); }
        catch { throw new Error('Unreadable response. Refresh before retrying; a submitted change may have applied.'); }
        if (!response.ok || !result.ok) throw new Error(result.error || 'Request failed. Refresh contacts.');
        if (!Array.isArray(result.contacts) || typeof result.public_key !== 'string') throw new Error('Incomplete contact response.');
        return result;
    }

    function contactDetails(contact) {
        const box = document.createElement('details'), summary = document.createElement('summary');
        summary.textContent = 'Details'; box.className = 'contact-details'; box.append(summary);
        const data = contact.details || {}, device = data.device || {};
        const zone = data.timezone || 'Europe/Berlin';
        const stamp = value => Number.isFinite(value) && value > 0 ? new Date(value * 1000).toLocaleString(undefined, {timeZone: zone}) + ' · ' + zone : 'Not available';
        function section(title, fields) {
            const heading = document.createElement('h4'), list = document.createElement('dl'); heading.textContent = title;
            for (const [label, value] of fields) { const term = document.createElement('dt'), definition = document.createElement('dd'); term.textContent = label; definition.textContent = value === undefined || value === null || value === '' ? 'Not available' : String(value); list.append(term, definition); }
            box.append(heading, list);
        }
        const mode = device.out_path_len === -1 ? 'Flooding' : device.out_path_len === 0 ? 'Direct (0 hops)' : device.out_path_len > 0 ? 'Saved route' : 'Not available';
        section('Companion contact', [['Name', contact.name], ['Type', (types[contact.type] || ['', 'Unknown'])[1] + ' (' + contact.type + ')'], ['Public key', contact.public_key],
            ['Latitude', contact.latitude], ['Longitude', contact.longitude], ['Last advertisement', stamp(device.last_advert)], ['Last modified', stamp(device.lastmod)],
            ['Routing mode', mode], ['Hop count', device.out_path_len >= 0 ? device.out_path_len : null], ['Path', device.out_path],
            ['Hash size', device.out_path_hash_mode >= 0 ? (device.out_path_hash_mode + 1) + ' bytes per hop' : null], ['Flags', device.flags]]);
        const repeater = data.repeater || {};
        section('Local repeater record', [['Name', repeater.name], ['First recorded', stamp(repeater.first_seen)], ['Last seen', stamp(repeater.last_seen)], ['Advertisement count', repeater.advert_count], ['Latitude', repeater.latitude], ['Longitude', repeater.longitude]]);
        const position = data.position || {};
        section('Locally saved position', [['Latitude', position.latitude], ['Longitude', position.longitude], ['Altitude', position.altitude], ['Updated', stamp(position.updated_at)]]);
        const battery = data.battery || {};
        section('Latest stored battery attempt', [['Voltage', Number.isFinite(battery.voltage) ? window.MeshcoreStationBattery.reading(battery.voltage) : null], ['Timestamp', stamp(battery.sampled_at)], ['Sensor channel', battery.voltage_channel], ['Error', battery.error || (battery.sampled_at ? 'None' : null)]]);
        const history = data.command_history || {};
        section('Recorded commands (matched public key)', [['Count', history.commands], ['Latest', stamp(history.last_command)]]);
        const raw = document.createElement('details'), rawTitle = document.createElement('summary'), pre = document.createElement('pre');
        rawTitle.textContent = 'All recorded fields'; pre.textContent = JSON.stringify(data, null, 2); raw.append(rawTitle, pre); box.append(raw);
        return box;
    }

    function render(result) {
        snapshot = result;
        byId('contacts-identity').textContent = `Connected companion: ${result.public_key}`;
        byId('contacts-count').textContent = `${result.contacts.length} contacts`;
        const list = byId('contacts-list'); list.replaceChildren();
        for (const contact of result.contacts) {
            const row = document.createElement('li'), icon = document.createElement('span');
            const text = document.createElement('div'), name = document.createElement('strong');
            const details = document.createElement('small'), button = document.createElement('button');
            const [symbol, label] = types[contact.type] || ['◆', `Type ${contact.type}`];
            icon.className = 'contact-icon'; icon.textContent = symbol; icon.setAttribute('aria-hidden', 'true');
            name.textContent = contact.name || '(unnamed)';
            details.textContent = `${label} · ${contact.public_key.slice(0, 12)}…`;
            details.title = contact.public_key;
            text.className = 'contact-label'; text.append(name, details, contactDetails(contact));
            button.type = 'button'; button.textContent = 'Delete'; button.className = 'contact-delete';
            button.setAttribute('aria-label', `Delete ${contact.name || contact.public_key}`);
            button.addEventListener('click', () => remove(contact));
            const actions = document.createElement('div'); actions.className = 'contact-actions';
            if (contact.type === 2) {
                const manage = document.createElement('button'); manage.type = 'button'; manage.textContent = 'Manage'; manage.className = 'contact-manage';
                manage.setAttribute('aria-label', `Manage ${contact.name || contact.public_key}`);
                manage.addEventListener('click', () => window.meshcorestationManageRepeater(contact)); actions.append(manage);
            }
            actions.append(button); row.append(icon, text, actions); list.append(row);
        }
        if (!result.contacts.length) {
            const empty = document.createElement('li'); empty.textContent = 'The companion has no saved contacts.'; list.append(empty);
        }
    }

    async function load() {
        if (busy) return;
        busy = true; snapshot = null; controls(); message('Reading contacts from the companion…');
        try { render(await request()); message('Contacts loaded from the companion.'); }
        catch (error) { message(error.message, true); }
        finally { busy = false; controls(); }
    }

    async function mutate(payload, success) {
        busy = true; controls(); message('Saving and verifying the contact list…');
        try {
            const result = await request(payload);
            if (result.public_key !== payload.expected_public_key) throw new Error('Companion changed. Refresh contacts.');
            render(result); message(success);
            return true;
        } catch (error) {
            snapshot = null;
            message(`${error.message} Use Refresh before another change.`, true);
            return false;
        } finally { busy = false; controls(); }
    }

    async function remove(contact) {
        if (busy || !snapshot) return;
        if (!window.confirm(`Delete ${contact.name || '(unnamed)'}?\n\n${contact.public_key}\n\nRemove this contact from the companion?`)) return;
        await mutate({operation: 'delete_contact', public_key: contact.public_key, expected: Object.fromEntries(['public_key','name','type','latitude','longitude'].map(k => [k, contact[k]])),
            expected_public_key: snapshot.public_key, confirm_delete: true}, 'Contact deletion verified.');
    }

    async function add(event) {
        event.preventDefault();
        if (busy || !snapshot || !byId('contact-form').reportValidity()) return;
        const name = byId('contact-name').value.trim(), key = byId('contact-key').value.trim().toLowerCase();
        if (!name || new TextEncoder().encode(name).length > 31 || /[\x00-\x1f\x7f]/.test(name)) {
            message('Use a name of 1–31 UTF-8 bytes without control characters.', true); return;
        }
        if (!/^[0-9a-f]{64}$/.test(key)) { message('Enter the full public key: exactly 64 hexadecimal characters.', true); return; }
        const value = {name, public_key: key, type: Number(byId('contact-type').value)};
        const lat = byId('contact-lat').value, lon = byId('contact-lon').value;
        if ((lat === '') !== (lon === '')) { message('Enter both coordinates or leave both empty.', true); return; }
        if (lat !== '') { value.latitude = Number(lat); value.longitude = Number(lon); }
        if (await mutate({operation: 'add_contact', expected_public_key: snapshot.public_key, value}, 'Contact addition verified.')) {
            byId('contact-form').reset(); byId('contact-form').hidden = true; byId('contacts-add').setAttribute('aria-expanded', 'false');
            byId('contacts-add').focus();
        }
    }

    function create() {
        dialog = document.createElement('dialog'); dialog.id = 'contacts-dialog'; dialog.setAttribute('aria-labelledby', 'contacts-title');
        dialog.innerHTML = `<div class="dialog-header"><h2 id="contacts-title">Companion contacts</h2><button type="button" id="contacts-close" aria-label="Close contacts">×</button></div>
            <p id="contacts-identity" class="muted"></p><div class="contacts-toolbar"><button type="button" id="contacts-refresh">Refresh</button><button type="button" id="contacts-add" class="info-button" aria-expanded="false" aria-controls="contact-form">Add contact</button><span id="contacts-count" class="muted"></span></div>
            <p id="contacts-message" role="status" aria-live="polite"></p>
            <form id="contact-form" hidden><h3>Add contact</h3><div class="contact-fields">
            <label>Type<select id="contact-type"><option value="1">Companion</option><option value="2">Repeater</option></select></label>
            <label>Name<input id="contact-name" maxlength="31" required autocomplete="off"></label>
            <label class="contact-key-field">Full public key<input id="contact-key" required maxlength="64" pattern="[0-9a-fA-F]{64}" spellcheck="false" autocomplete="off"></label>
            <label>Latitude (optional)<input id="contact-lat" type="number" min="-90" max="90" step="any"></label>
            <label>Longitude (optional)<input id="contact-lon" type="number" min="-180" max="180" step="any"></label></div>
            <p class="muted">Enter both coordinates or leave both empty. The contact starts with an unknown route.</p>
            <div class="contacts-toolbar"><button type="submit" class="info-button">Save contact</button><button type="button" id="contact-cancel">Cancel</button></div></form>
            <ul id="contacts-list"></ul>`;
        window.meshcorestationPrepareDialog(dialog);
        document.body.append(dialog);
        byId('contacts-close').addEventListener('click', close);
        dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
        byId('contacts-refresh').addEventListener('click', load);
        byId('contact-form').addEventListener('submit', add);
        byId('contacts-add').addEventListener('click', () => {
            byId('contact-form').hidden = false; byId('contacts-add').setAttribute('aria-expanded', 'true'); byId('contact-name').focus();
        });
        byId('contact-cancel').addEventListener('click', () => {
            if (dirty() && !window.confirm('Discard the unfinished contact?')) return;
            byId('contact-form').reset(); byId('contact-form').hidden = true; byId('contacts-add').setAttribute('aria-expanded', 'false'); byId('contacts-add').focus();
        });
    }

    function attach() {
        const settings = byId('open-companion');
        if (!settings || byId('open-contacts')) return;
        const button = document.createElement('button'); button.id = 'open-contacts'; button.type = 'button';
        button.className = 'info-button'; button.textContent = 'Contacts';
        settings.insertAdjacentElement('afterend', button);
        settings.parentElement.classList.add('has-contacts');
    }

    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
    document.addEventListener('click', event => {
        if (!event.target.closest('#open-contacts')) return;
        if (!dialog) create();
        if (dialog.open) return;
        snapshot = null; byId('contact-form').reset(); byId('contact-form').hidden = true;
        byId('contacts-add').setAttribute('aria-expanded', 'false');
        byId('contacts-list').replaceChildren(); byId('contacts-count').textContent = ''; byId('contacts-identity').textContent = '';
        dialog.showModal(); load();
    });
    attach();
})();