(() => {
    const {translatedError: uiError, t: ui, html: uiHTML} = window.MeshcoreStationI18n || {
        translatedError: value => value,
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`)),
        html: value => value
    };
    let dialog, snapshot = null, busy = false;
    const byId = id => document.getElementById(id);
    const types = {1: ['📱', ui("Companion")], 2: ['📡', ui("Repeater")], 3: ['💬', ui("Room")], 4: ['🌡️', ui("Sensor")]};

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
        if (!busy && (!dirty() || window.confirm(ui("Discard the unfinished contact?")))) dialog.close();
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
        catch { throw new Error(ui("Unreadable response. Refresh before retrying; a submitted change may have applied.")); }
        if (!response.ok || !result.ok) throw new Error(result.error || ui("Request failed. Refresh contacts."));
        if (!Array.isArray(result.contacts) || typeof result.public_key !== 'string') throw new Error(ui("Incomplete contact response."));
        return result;
    }

    function contactDetails(contact) {
        const box = document.createElement('details'), summary = document.createElement('summary');
        summary.textContent = ui("Details"); box.className = 'contact-details'; box.append(summary);
        const data = contact.details || {}, device = data.device || {};
        const zone = data.timezone || 'Europe/Berlin';
        const stamp = value => Number.isFinite(value) && value > 0 ? window.meshcorestationFormatDate(value,zone) + ' · ' + zone : ui("Not available");
        function section(title, fields) {
            const heading = document.createElement('h4'), list = document.createElement('dl'); heading.textContent = title;
            for (const [label, value] of fields) { const term = document.createElement('dt'), definition = document.createElement('dd'); term.textContent = label; definition.textContent = value === undefined || value === null || value === '' ? ui("Not available") : String(value); list.append(term, definition); }
            box.append(heading, list);
        }
        const mode = device.out_path_len === -1 ? ui("Flooding") : device.out_path_len === 0 ? ui("Direct (0 hops)") : device.out_path_len > 0 ? ui("Saved route") : ui("Not available");
        section(ui("Companion contact"), [[ui("Name"), contact.name], [ui("Type"), (types[contact.type] || ['', ui("Unknown")])[1] + ' (' + contact.type + ')'], [ui("Public key"), contact.public_key],
            [ui("Latitude"), contact.latitude], [ui("Longitude"), contact.longitude], [ui("Last advertisement"), stamp(device.last_advert)], [ui("Last modified"), stamp(device.lastmod)],
            [ui("Routing mode"), mode], [ui("Hop count"), device.out_path_len >= 0 ? device.out_path_len : null], [ui("Path"), device.out_path],
            [ui("Hash size"), device.out_path_hash_mode >= 0 ? (device.out_path_hash_mode + 1) + ui(" bytes per hop") : null], [ui("Flags"), device.flags]]);
        const repeater = data.repeater || {};
        section(ui("Local repeater record"), [[ui("Name"), repeater.name], [ui("First recorded"), stamp(repeater.first_seen)], [ui("Last seen"), stamp(repeater.last_seen)], [ui("Advertisement count"), repeater.advert_count], [ui("Latitude"), repeater.latitude], [ui("Longitude"), repeater.longitude]]);
        const position = data.position || {};
        section(ui("Locally saved position"), [[ui("Latitude"), position.latitude], [ui("Longitude"), position.longitude], [ui("Altitude"), position.altitude], [ui("Updated"), stamp(position.updated_at)]]);
        const battery = data.battery || {};
        section(ui("Latest stored battery attempt"), [[ui("Voltage"), Number.isFinite(battery.voltage) ? window.MeshcoreStationBattery.reading(battery.voltage) : null], [ui("Timestamp"), stamp(battery.sampled_at)], [ui("Sensor channel"), battery.voltage_channel], [ui("Error"), battery.error || (battery.sampled_at ? ui("None") : null)]]);
        const history = data.command_history || {};
        section(ui("Recorded commands (matched public key)"), [[ui("Count"), history.commands], [ui("Latest"), stamp(history.last_command)]]);
        const raw = document.createElement('details'), rawTitle = document.createElement('summary'), pre = document.createElement('pre');
        rawTitle.textContent = ui("All recorded fields"); pre.textContent = JSON.stringify(data, null, 2); raw.append(rawTitle, pre); box.append(raw);
        return box;
    }

    function render(result) {
        snapshot = result;window.MeshcoreStationRepeaterNames?.ingest(result.contacts.filter(c=>c.type===2));
        byId('contacts-identity').textContent = ui("Connected companion: {0}", result.public_key);
        byId('contacts-count').textContent = ui("{0} contacts", result.contacts.length);
        const list = byId('contacts-list'); list.replaceChildren();
        for (const contact of result.contacts) {
            const row = document.createElement('li'), icon = document.createElement('span');
            const text = document.createElement('div'), name = document.createElement('strong');
            const details = document.createElement('small'), button = document.createElement('button');
            const [symbol, label] = types[contact.type] || ['◆', ui("Type {0}", contact.type)];
            icon.className = 'contact-icon'; icon.textContent = symbol; icon.setAttribute('aria-hidden', 'true');
            if(contact.type===2&&window.MeshcoreStationRepeaterNames){name.dataset.repeaterKey=contact.public_key;name.textContent=window.MeshcoreStationRepeaterNames.label(contact.public_key);name.title=contact.public_key;}else name.textContent = contact.name || '(unnamed)';
            details.textContent = contact.type===2?label:`${label} · ${contact.public_key.slice(0,12)}…`;
            details.title = contact.public_key;
            text.className = 'contact-label'; text.append(name, details, contactDetails(contact));
            button.type = 'button'; button.textContent = ui("Delete"); button.className = 'contact-delete';
            button.setAttribute('aria-label', ui("Delete {0}", contact.name || contact.public_key));
            button.addEventListener('click', () => remove(contact));
            const actions = document.createElement('div'); actions.className = 'contact-actions';
            if (contact.type === 2) {
                const manage = document.createElement('button'); manage.type = 'button'; manage.textContent = ui("Manage"); manage.className = 'contact-manage';
                manage.setAttribute('aria-label', ui("Manage {0}", contact.name || contact.public_key));
                manage.addEventListener('click', () => window.meshcorestationManageRepeater(contact)); actions.append(manage);
            }
            actions.append(button); row.append(icon, text, actions); list.append(row);
        }
        if (!result.contacts.length) {
            const empty = document.createElement('li'); empty.textContent = ui("The companion has no saved contacts."); list.append(empty);
        }
    }

    async function load() {
        if (busy) return;
        busy = true; snapshot = null; controls(); message(ui("Reading contacts from the companion…"));
        try { render(await request()); message(ui("Contacts loaded from the companion.")); }
        catch (error) { message(uiError(error.message), true); }
        finally { busy = false; controls(); }
    }

    async function mutate(payload, success) {
        busy = true; controls(); message(ui("Saving and verifying the contact list…"));
        try {
            const result = await request(payload);
            if (result.public_key !== payload.expected_public_key) throw new Error(ui("Companion changed. Refresh contacts."));
            render(result); message(success);
            return true;
        } catch (error) {
            snapshot = null;
            message(ui("{0} Use Refresh before another change.", error.message), true);
            return false;
        } finally { busy = false; controls(); }
    }

    async function remove(contact) {
        if (busy || !snapshot) return;
        if (!window.confirm(ui("Delete {0}?\n\n{1}\n\nRemove this contact from the companion?", contact.name || '(unnamed)', contact.public_key))) return;
        await mutate({operation: 'delete_contact', public_key: contact.public_key, expected: Object.fromEntries(['public_key','name','type','latitude','longitude'].map(k => [k, contact[k]])),
            expected_public_key: snapshot.public_key, confirm_delete: true}, ui("Contact deletion verified."));
    }

    async function add(event) {
        event.preventDefault();
        if (busy || !snapshot || !byId('contact-form').reportValidity()) return;
        const name = byId('contact-name').value.trim(), key = byId('contact-key').value.trim().toLowerCase();
        if (!name || new TextEncoder().encode(name).length > 31 || /[\x00-\x1f\x7f]/.test(name)) {
            message(ui("Use a name of 1–31 UTF-8 bytes without control characters."), true); return;
        }
        if (!/^[0-9a-f]{64}$/.test(key)) { message(ui("Enter the full public key: exactly 64 hexadecimal characters."), true); return; }
        const value = {name, public_key: key, type: Number(byId('contact-type').value)};
        const lat = byId('contact-lat').value, lon = byId('contact-lon').value;
        if ((lat === '') !== (lon === '')) { message(ui("Enter both coordinates or leave both empty."), true); return; }
        if (lat !== '') { value.latitude = Number(lat); value.longitude = Number(lon); }
        if (await mutate({operation: 'add_contact', expected_public_key: snapshot.public_key, value}, ui("Contact addition verified."))) {
            byId('contact-form').reset(); byId('contact-form').hidden = true; byId('contacts-add').setAttribute('aria-expanded', 'false');
            byId('contacts-add').focus();
        }
    }

    function create() {
        dialog = document.createElement('dialog'); dialog.id = 'contacts-dialog'; dialog.setAttribute('aria-labelledby', 'contacts-title');
        dialog.innerHTML = uiHTML(`<div class="dialog-header"><h2 id="contacts-title">Companion contacts</h2><button type="button" id="contacts-close" aria-label="Close contacts">×</button></div>
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
            <ul id="contacts-list"></ul>`);
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
            if (dirty() && !window.confirm(ui("Discard the unfinished contact?"))) return;
            byId('contact-form').reset(); byId('contact-form').hidden = true; byId('contacts-add').setAttribute('aria-expanded', 'false'); byId('contacts-add').focus();
        });
    }

    function attach() {
        const settings = byId('open-companion');
        if (!settings || byId('open-contacts')) return;
        const button = document.createElement('button'); button.id = 'open-contacts'; button.type = 'button';
        button.className = 'info-button'; button.textContent = ui("Contacts");
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