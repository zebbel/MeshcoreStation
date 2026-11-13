/* Remote repeater management. Session tokens stay in this page; login passwords are saved only by opt-in. */
(() => {
    const {translatedError: uiError, t: ui, html: uiHTML} = window.MeshcoreStationI18n || {
        translatedError: value => value,
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`)),
        html: value => value
    };
    let loginDialog, dialog, commandDialog, contact, session = '', admin = false, busy = false, schema = {}, selectedTab = 'status';
    const values = new Map(), inputs = new Map(), loaded = new Set();
    const $ = id => document.getElementById(id);
    const passwordKey = () => 'meshcorestation.repeater.password.' + contact.public_key.toLowerCase();
    function savedPassword() {
        try { return localStorage.getItem(passwordKey()) || ''; } catch { return ''; }
    }
    function savePassword(password) {
        try {
            if (password) localStorage.setItem(passwordKey(), password);
            else localStorage.removeItem(passwordKey());
            return true;
        } catch { return false; }
    }
    function node(tag, text, cls) { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; if (cls) item.className = cls; return item; }
    function button(text, handler, cls) { const item = node('button', text, cls); item.type = 'button'; item.addEventListener('click', handler); return item; }
    function message(text, error = false) { const box = $('repeater-message'); box.textContent = text; box.classList.toggle('repeater-error', error); }
    function controls() {
        for (const root of [dialog, loginDialog]) if (root) {
            root.setAttribute('aria-busy', String(busy));
            root.querySelectorAll('button,input,select,textarea').forEach(item => { item.disabled = busy || item.dataset.unavailable === 'true' || ((item.closest('#repeater-config') || item.closest('#repeater-console-form')) && (!admin || !session)); });
        }
        inputs.forEach((input, field) => { input.disabled = busy || !admin || !session || (schema[field].kind !== 'password' && !values.has(field)); });
        if ($('repeater-choose-map')) $('repeater-choose-map').disabled = !canPickLocation();
    }
    async function request(payload) {
        const response = await fetch('/api/repeater', {method: 'POST', cache: 'no-store', headers: {'Content-Type': 'application/json', 'X-Meshcore-Control': '1'}, body: JSON.stringify({...payload, public_key: contact.public_key, session})});
        let result;
        try { result = await response.json(); } catch { throw new Error(ui("Unreadable response. A submitted change may have applied; read before retrying.")); }
        if (result.expired) { session = ''; admin = false; $('repeater-reconnect').hidden = false; }
        if (!response.ok || !result.ok) throw new Error(result.error || ui("Repeater request failed."));
        if (typeof result.admin === 'boolean') admin = result.admin;
        return result;
    }
    async function run(work, report = message) {
        if (busy) return;
        busy = true; controls();
        try { await work(); } catch (error) { report(uiError(error.message), true); }
        finally { busy = false; controls(); }
    }
    function dirty() { return [...inputs].some(([field, input]) => schema[field].kind === 'password' ? input.value !== '' : values.has(field) && input.value !== values.get(field)); }
    function forget() {
        if (session) {
            // Retire the server token on close; no remote logout that would disturb monitoring.
            fetch('/api/repeater', {method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json', 'X-Meshcore-Control': '1'}, body: JSON.stringify({action: 'logout', public_key: contact.public_key, session})}).catch(() => {});
        }
        $('repeater-console-log').textContent='';$('repeater-console-command').value='';
        session = ''; inputs.forEach(input => { if (input.type === 'password') input.value = ''; });
    }
    function close() {
        if (busy || (dirty() && !window.confirm(ui("Discard unsaved repeater edits?")))) return;
        forget(); dialog.close();
    }
    function tab(name) {
        selectedTab = name;
        for (const value of ['status', 'config', 'console']) {
            const active = value === name;
            $('repeater-tab-' + value).setAttribute('aria-selected', String(active));
            $('repeater-tab-' + value).tabIndex = active ? 0 : -1;
            $('repeater-' + value).hidden = !active;
        }
    }
    function create() {
        dialog = node('dialog'); dialog.id = 'repeater-manage-dialog'; dialog.setAttribute('aria-labelledby', 'repeater-title');
        dialog.innerHTML = uiHTML(`<div class="dialog-header"><h2 id="repeater-title">Repeater management</h2><button type="button" id="repeater-close" aria-label="Close repeater management">×</button></div>
            <div class="repeater-fixed"><strong id="repeater-name"></strong><p id="repeater-identity" class="muted"></p><div class="repeater-tabs" role="tablist" aria-label="Repeater management">
            <button type="button" id="repeater-tab-status" role="tab" aria-controls="repeater-status">Status</button><button type="button" id="repeater-tab-config" role="tab" aria-controls="repeater-config">Configurations</button><button type="button" id="repeater-tab-console" role="tab" aria-controls="repeater-console">Console</button></div></div>
            <div class="dialog-body"><p id="repeater-message" role="status" aria-live="polite"></p><button type="button" id="repeater-reconnect" hidden>Connect again</button>
            <section id="repeater-status" role="tabpanel" aria-labelledby="repeater-tab-status"><div class="repeater-toolbar"><span id="repeater-last-response" class="muted">Not yet read</span><button type="button" id="repeater-refresh">↻ Refresh</button></div><div id="repeater-status-cards"></div><div id="repeater-extras"></div></section>
            <section id="repeater-config" role="tabpanel" aria-labelledby="repeater-tab-config" hidden></section>
            <section id="repeater-console" role="tabpanel" aria-labelledby="repeater-tab-console" hidden><p class="muted">Send remote CLI commands as administrator. Commands run immediately and are not retried. Available commands depend on repeater firmware; serial-only commands cannot run over radio.</p><pre id="repeater-console-log" class="repeater-data" role="log" aria-label="Repeater console output" aria-live="polite"></pre><form id="repeater-console-form"><label for="repeater-console-command">Command</label><div class="repeater-toolbar"><input id="repeater-console-command" placeholder="e.g. get name" autocomplete="off" spellcheck="false" maxlength="147" required><button type="button" id="repeater-console-commands">Commands…</button><button type="submit">Send</button></div></form><button type="button" id="repeater-console-clear">Clear console</button><p class="muted">History is kept only while this management window is open. Password and private-key command text and replies are hidden. After using the console, read configuration values again before saving.</p></section></div>`);
        document.body.append(dialog);
        $('repeater-close').addEventListener('click', close);
        dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
        $('repeater-refresh').addEventListener('click', () => run(readStatus));
        $('repeater-reconnect').addEventListener('click', () => { if (dirty() && !window.confirm(ui("Discard unsaved edits and reconnect?"))) return; forget(); dialog.close(); openLogin(); });
        for (const name of ['status', 'config', 'console']) $('repeater-tab-' + name).addEventListener('click', () => tab(name));
        dialog.querySelector('[role="tablist"]').addEventListener('keydown', event => {
            if (busy || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault(); const tabs=['status','config','console'];
            tab(event.key==='Home'?tabs[0]:event.key==='End'?tabs.at(-1):tabs[(tabs.indexOf(selectedTab)+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length]);
            $('repeater-tab-' + selectedTab).focus();
        });
        $('repeater-console-commands').onclick = openCommandPicker;
        $('repeater-console-clear').onclick=()=>{$('repeater-console-log').textContent='';};
        $('repeater-console-form').onsubmit=event=>{
            event.preventDefault();if(busy || !admin || !session)return;
            const input=$('repeater-console-command'),command=input.value.trim();
            if(!command)return;
            if(/<[^>]+>/.test(command)){message(ui("Replace the command placeholders before sending."),true);return;}
            if(dirty() && !window.confirm(ui("Discard unsaved configuration edits before sending a console command?")))return;
            if(new TextEncoder().encode(command).length>147){message(ui("Use at most 147 UTF-8 bytes."),true);return;}
            const secret=/^(password(?: |$)|(?:get|set) (?:guest\.password|bridge\.secret|prv\.key)(?: |$))/.test(command);
            if(!/^(get |ver$|board$|clock$|neighbors$|region$|sensor (list|get)\b|gps$|powersaving$)/.test(command) && !window.confirm(ui("Send this command to ")+contact.name+ui("? It may change repeater settings or interrupt connectivity.")))return;
            input.value='';
            run(async()=>{
                consoleLine('> '+(secret?ui("[sensitive command]"):command));
                values.clear();loaded.clear();inputs.forEach(entry=>{entry.value='';const hint=$(entry.id+'-hint');if(hint)hint.textContent=ui("Read again after console command.");});
                try{const result=await request({action:'console',command,confirm:true});consoleLine(result.reply);message(ui("Console command finished. Read configuration sections again before editing."));}
                catch(error){consoleLine(ui("Error: ")+error.message);throw error;}
            });
        };
        loginDialog = node('dialog'); loginDialog.id = 'repeater-login-dialog'; loginDialog.setAttribute('aria-labelledby', 'repeater-login-title');
        loginDialog.innerHTML = uiHTML(`<div class="dialog-header"><h2 id="repeater-login-title">Connect to repeater</h2><button type="button" id="repeater-login-close" aria-label="Close repeater login">×</button></div><div class="dialog-body"><p id="repeater-login-name"></p><form id="repeater-login-form"><label for="repeater-password">Admin password</label><div class="repeater-password"><input id="repeater-password" type="password" autocomplete="off"><button type="button" id="repeater-show-password" aria-label="Show password">Show</button></div><label class="repeater-remember"><input id="repeater-remember-password" type="checkbox" aria-describedby="repeater-remember-help"> Remember password</label><p class="muted" id="repeater-remember-help">Leave blank to use existing permissions or guest access. Remembered passwords are stored in this browser on this device. Uncheck to forget.</p><p id="repeater-login-message" role="status" aria-live="polite"></p><button type="submit">Connect</button></form></div>`);
        document.body.append(loginDialog);
        const closeLogin = () => { if (!busy) { $('repeater-password').value = ''; loginDialog.close(); } };
        $('repeater-remember-password').addEventListener('change', () => {
            if (!$('repeater-remember-password').checked && !savePassword('')) {
                $('repeater-login-message').textContent = ui("Could not remove the saved password. Clear this site’s browser data to forget it.");
            }
        });
        $('repeater-login-close').addEventListener('click', closeLogin);
        loginDialog.addEventListener('cancel', event => { event.preventDefault(); closeLogin(); });
        $('repeater-show-password').addEventListener('click', () => { const input = $('repeater-password'), show = input.type === 'password'; input.type = show ? 'text' : 'password'; $('repeater-show-password').textContent = show ? ui("Hide") : ui("Show"); });
        $('repeater-login-form').addEventListener('submit', async event => {
            event.preventDefault(); if (busy) return;
            busy = true; controls(); $('repeater-login-message').textContent = ui("Connecting… This can take up to 40 seconds.");
            const password = $('repeater-password').value; $('repeater-password').value = '';
            try {
                const result = await request({action: 'login', password});
                const remembered = savePassword($('repeater-remember-password').checked ? password : '');
                session = result.session; admin = result.admin; schema = result.fields;
                values.clear(); inputs.clear(); loaded.clear(); buildConfig(); buildExtras();
                $('repeater-name').replaceChildren(window.MeshcoreStationRepeaterNames?.element(contact.public_key)||node('span',contact.name||ui("(unnamed repeater)")));
                identity(result.contact); $('repeater-reconnect').hidden = true;
                $('repeater-status-cards').replaceChildren(); $('repeater-last-response').textContent = ui("Not yet read");
                loginDialog.close(); tab('status'); dialog.showModal();
                await readStatus();
                if (!remembered) message(ui("Connected, but browser storage is unavailable. The remember-password choice could not be saved."), true);
            } catch (error) {
                if (dialog.open) message(uiError(error.message), true); else $('repeater-login-message').textContent = uiError(error.message);
            } finally { busy = false; controls(); }
        });
    }
    function consoleCommands() {
        const commands = [
            ['ver', ui("Show the repeater firmware version.")],
            ['board', ui("Show the repeater board model.")],
            ['clock', ui("Read the repeater clock.")],
            ['time <unix-seconds>', ui("Set the repeater clock to a Unix timestamp.")],
            ['advert', ui("Transmit an advertisement so nearby nodes can discover this repeater.")],
            ['neighbors', ui("List neighboring nodes heard by the repeater.")],
            ['region', ui("List the forwarding regions.")],
            ['region put <name> <parent>', ui("Create a region or change its parent; use * for the root.")],
            ['region remove <name>', ui("Remove a forwarding region.")],
            ['region allowf <name>', ui("Allow flood forwarding in a region.")],
            ['region denyf <name>', ui("Block flood forwarding in a region.")],
            ['region home <name>', ui("Select the home region.")],
            ['region default <name>', ui("Select the default outgoing scope.")],
            ['region save', ui("Save region changes so they survive a restart.")],
            ['setperm <public-key> <permission>', ui("Set companion access: 0 guest, 1 read-only, 2 read-write, 3 admin.")],
            ['sensor list', ui("List sensors supported by this firmware.")],
            ['sensor get <name>', ui("Read a sensor setting; names depend on the firmware.")],
            ['sensor set <name> <value>', ui("Change a sensor setting supported by this firmware.")],
            ['get extra.sf', ui("Read extra spreading factors on supported radios.")],
            ['set extra.sf <values>', ui("Configure extra spreading factors on supported radios; use a comma-separated list.")],
            ['reboot', ui("Restart the repeater. The management connection will end.")],
            ['powersaving', ui("Show whether power saving is enabled.")],
            ['gps', ui("Show GPS state and fix information on supported boards.")],
        ];
        for (const [field, spec] of Object.entries(schema)) {
            const label = ui(spec.label);
            if (spec.kind !== 'password') {
                const read = spec.read || 'get ' + field;
                if (!commands.some(([command]) => command === read)) commands.push([read, ui("Read ") + label + '.']);
            }
            const choices = spec.options ? ui(" Allowed values: ") + spec.options.join(', ') + '.' :
                spec.kind === 'number' ? ui(" Range: {0}–{1}{2}.", spec.low, spec.high, spec.step ? ui(", step ") + spec.step : '') : '';
            const argument = spec.kind === 'radio' ? '<frequency>,<bandwidth>,<sf>,<cr>' : '<value>';
            commands.push([(spec.write || 'set ' + field) + ' ' + argument, ui("Change ") + label + '.' + choices]);
        }
        return commands;
    }
    function openCommandPicker() {
        if (busy || !admin || !session) return;
        if (!commandDialog) {
            commandDialog = node('dialog'); commandDialog.id = 'repeater-command-dialog';
            commandDialog.setAttribute('aria-labelledby', 'repeater-command-title');
            commandDialog.innerHTML = uiHTML(`<div class="dialog-header"><h2 id="repeater-command-title">Console commands</h2><button type="button" id="repeater-command-close" aria-label="Close command picker">×</button></div><div class="dialog-body"><p class="muted">Choose a command to insert it without sending. Replace values in &lt;angle brackets&gt; before pressing Send. Availability depends on repeater firmware and hardware.</p><label for="repeater-command-search">Find a command</label><input id="repeater-command-search" type="search" placeholder="Search commands or descriptions" autocomplete="off"><div id="repeater-command-list"></div></div>`);
            document.body.append(commandDialog);
            $('repeater-command-close').onclick = () => commandDialog.close();
        }
        const search = $('repeater-command-search'), list = $('repeater-command-list');
        const render = () => {
            list.replaceChildren();
            const query = search.value.trim().toLowerCase();
            for (const [command, purpose] of consoleCommands()) {
                if (!(command + ' ' + purpose).toLowerCase().includes(query)) continue;
                const choice = button('', () => {
                    const input = $('repeater-console-command');
                    input.value = command;
                    commandDialog.close(); input.focus();
                    const placeholder = /<[^>]+>/.exec(command);
                    if (placeholder) input.setSelectionRange(placeholder.index, placeholder.index + placeholder[0].length);
                }, 'repeater-command-choice');
                choice.append(node('code', command), node('span', purpose)); list.append(choice);
            }
            if (!list.children.length) list.append(node('p', ui("No matching commands."), 'muted'));
        };
        search.value = ''; search.oninput = render; render(); commandDialog.showModal(); search.focus();
    }
    function consoleLine(text) {
        const log=$('repeater-console-log');
        log.textContent=(log.textContent+window.meshcorestationFormatDate(new Date(),undefined,{timeOnly:true})+' '+text+'\n').slice(-24000);
        log.scrollTop=log.scrollHeight;
    }
    function identity(info) {
        const hops = info.out_path_len;
        $('repeater-identity').textContent = contact.public_key.slice(0, 12) + '… · ' + (hops === 0 ? ui("Direct") : hops > 0 ? ui('{0} hops', hops) : ui("Flood route")) + (admin ? '' : ui(" · Guest access"));
        $('repeater-identity').title = contact.public_key;
    }

    // Same-origin embedded advisor; credentials and radio session stay in management.
    const advisorFields = ['flood.max','flood.max.unscoped'];
    function openLogin() {
        $('repeater-login-name').replaceChildren(window.MeshcoreStationRepeaterNames?.element(contact.public_key)||node('span',contact.name||contact.public_key));
        $('repeater-login-message').textContent = ''; $('repeater-password').value = savedPassword();
        $('repeater-remember-password').checked = $('repeater-password').value !== ''; $('repeater-password').type = 'password'; $('repeater-show-password').textContent = ui("Show");
        controls(); loginDialog.showModal(); $('repeater-password').focus();
    }
    document.addEventListener('managed-repeater-selected',()=>{
        if(dialog&&contact?.public_key!==window.meshcorestationSelectedRepeater){forget();if(dialog.open)dialog.close();if(loginDialog.open)loginDialog.close();}
    });
    window.meshcorestationManageRepeater = selected => {
        if (busy || selected.type !== 2) return;
        if (!dialog) create();
        if (dialog.open || loginDialog.open) return;
        if(session)forget();
        window.MeshcoreStationRepeaterNames?.ingest([selected]);
        contact = {...selected}; session = ''; admin = false; openLogin();
    };
    const duration = value => { if (!Number.isFinite(value)) return ui("Not available"); const seconds = Math.max(0, Math.floor(value)); return `${Math.floor(seconds / 86400)}d ${Math.floor(seconds / 3600) % 24}h ${Math.floor(seconds / 60) % 60}m`; };
    const unit = (value, suffix = '') => Number.isFinite(value) ? value + suffix : ui("Not available");
    function card(title, rows) {
        const section = node('section', undefined, 'repeater-section'), list = node('dl'); section.append(node('h3', title));
        for (const [label, value] of rows) list.append(node('dt', label), node('dd', value));
        section.append(list); return section;
    }
    async function readStatus() {
        message(ui("Reading repeater status…"));
        const result = await request({action: 'status'}), data = result.data, cards = $('repeater-status-cards');
        identity(result.contact);
        const clock = Number.isInteger(result.repeater_time) && result.repeater_time >= 0
            ? window.meshcorestationFormatDate(result.repeater_time,'Europe/Berlin') + ui(" · Europe/Berlin (") + window.meshcorestationFormatDate(result.repeater_time,'UTC')+' UTC' + ')'
            : ui("Not reported by repeater firmware");
        cards.replaceChildren(card(ui("System"), [[ui("Repeater clock (last read)"), clock], [ui("Battery"), Number.isFinite(data.bat) ? window.MeshcoreStationBattery.reading(data.bat / 1000) : ui("Not available")], [ui("Uptime"), duration(data.uptime)], [ui("Queue"), unit(data.tx_queue_len)], [ui("Firmware level"), unit(result.firmware_level)], [ui("Debug events"), unit(data.full_evts)]]),
            card(ui("Radio"), [[ui("Last RSSI"), unit(data.last_rssi, ' dBm')], [ui("Last SNR"), unit(data.last_snr, ' dB')], [ui("Noise floor"), unit(data.noise_floor, ' dBm')], [ui("TX airtime"), duration(data.airtime)], [ui("RX airtime"), duration(data.rx_airtime)], [ui("Receive errors"), unit(data.recv_errors)]]));
        const packet = node('section', undefined, 'repeater-section'); packet.append(node('h3', ui("Packets")));
        packet.append(table([ui("Type"), ui("Sent"), ui("Received")], [[ui("Flood"), unit(data.sent_flood), unit(data.recv_flood)], [ui("Direct"), unit(data.sent_direct), unit(data.recv_direct)], [ui("Total"), unit(data.nb_sent), unit(data.nb_recv)]]));
        packet.append(node('p', ui("Duplicates · Flood: ") + unit(data.flood_dups) + ui(" · Direct: ") + unit(data.direct_dups), 'muted')); cards.append(packet);
        $('repeater-last-response').textContent = ui("Last response: ") + window.meshcorestationFormatDate(result.sampled_at,'Europe/Berlin') + ui(" · Europe/Berlin");
        message(admin ? ui("Status received.") : ui("Guest session: status is available; configurations require administrator access."));
    }
    function table(headings, rows) {
        const grid = node('table'), head = node('thead'), tr = node('tr'), body = node('tbody');
        headings.forEach(label => tr.append(node('th', label))); head.append(tr);
        rows.forEach(row => { const line = node('tr'); row.forEach(value => {const cell=node('td');if(value instanceof Node)cell.append(value);else cell.textContent=typeof value==='object'?JSON.stringify(value):String(value??ui("Not available"));line.append(cell);}); body.append(line); });
        grid.append(head, body); return grid;
    }
    function disclosure(title, subtitle) {
        const details = node('details', undefined, 'repeater-section'), summary = node('summary'); summary.append(node('strong', title));
        if (subtitle) summary.append(node('small', subtitle, 'muted')); details.append(summary); return details;
    }
    function buildExtras() {
        const root = $('repeater-extras'); root.replaceChildren();
        for (const [action, label] of [['telemetry', ui("Telemetry")], ['neighbors', ui("Neighbors")]]) {
            const box = disclosure(label), content = node('div', undefined, 'repeater-extra-content');
            const localMessage = node('p', '', 'muted');
            localMessage.setAttribute('role', 'status'); localMessage.setAttribute('aria-live', 'polite');
            if (action === 'neighbors') localMessage.id = 'repeater-neighbors-message';
            const report = action === 'neighbors' ? (text, error = false) => { localMessage.textContent = text; localMessage.classList.toggle('repeater-error', error); } : message;
            let offset = 0;
            const load = async (more = false) => {
                report(ui("Reading ") + label.toLowerCase() + '…');
                const result = await request({action, offset: more ? offset : 0});
                if (!more) content.replaceChildren();
                if (action === 'neighbors') {
                    const data = result.data, rows = data.neighbours || [];
                    window.MeshcoreStationRepeaterNames?.ingest(rows,'local');
                    content.append(table([ui("Repeater"), ui("Last heard"), 'SNR'], rows.map(row => [row.public_key ? (window.MeshcoreStationRepeaterNames?.element(row.public_key)||row.name||row.public_key) : row.name||(ui("Unknown Repeater (")+row.pubkey+'…)'), duration(row.secs_ago) + ' ago', unit(row.snr, ' dB')])));
                    offset = (more ? offset : 0) + rows.length;
                    next.hidden = offset >= data.neighbours_count || rows.length === 0;
                    content.append(node('p', ui("{0} / {1} neighbors", offset, data.neighbours_count), 'muted'));
                } else {
                    if (Array.isArray(result.data)) content.append(result.data.length ? table([ui("Channel"), ui("Sensor"), ui("Value")], result.data.map(row => [row.channel, row.type, Number.isFinite(row.value) && row.type === 'voltage' ? row.value.toFixed(2) + ' V' : Number.isFinite(row.value) && row.type === 'temperature' ? row.value.toFixed(1) + ' °C' : row.value])) : node('p', ui("The repeater returned no sensor readings.")));
                    else content.append(node('pre', JSON.stringify(result.data, null, 2), 'repeater-data'));
                }
                loaded.add(action);
                report(label + ' received.');
            };
            const refresh = button(ui("↻ Refresh"), () => run(() => load(), report)), next = button(ui("Load more"), () => run(() => load(true), report)); next.hidden = true;
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
        const label = node(spec.kind === 'radio' ? 'div' : 'label', ui(spec.label), 'repeater-field'); let input;
        if (spec.kind === 'radio') {
            input = node('fieldset', undefined, 'repeater-radio-fields'); input.append(node('legend', ui("Radio parameters")));
            for (const [name, placeholder] of [[ui("Frequency (MHz)"), '868.000'], [ui("Bandwidth (kHz)"), '62.5'], [ui("Spreading factor"), '7'], [ui("Coding rate"), '5']]) {
                const part = node('label', name), entry = node('input'); entry.type = 'number'; entry.step = 'any'; entry.placeholder = placeholder; entry.setAttribute('aria-label', name); part.append(entry); input.append(part);
            }
            // A value property lets shared dirty-state handling treat this group as one field.
            Object.defineProperty(input, 'value', {get: () => [...input.querySelectorAll('input')].map(i => i.value).join(',')});
        } else if (spec.kind === 'select') {
            input = node('select'); spec.options.forEach((value, i) => { const option = node('option', ui(spec.labels?.[i] || value)); option.value = value; input.append(option); });
        } else {
            input = node(spec.kind === 'textarea' ? 'textarea' : 'input');
            if (input.tagName === 'INPUT') input.type = spec.kind === 'password' ? 'password' : spec.kind === 'number' ? 'number' : 'text';
            if (spec.kind === 'number') { input.min = spec.low; input.max = spec.high; input.step = spec.step || 'any'; }
            if (spec.kind === 'password') { input.autocomplete = 'new-password'; input.placeholder = ui("Leave blank to keep unchanged"); }
        }
        input.id = 'repeater-field-' + field.replaceAll('.', '-'); input.setAttribute('aria-label', ui(spec.label)); inputs.set(field, input);
        label.append(input); const hint = node('small', spec.kind === 'password' ? ui("Write-only; not saved in MeshcoreStation.") : ui("Read this section to load the current value."), 'muted'); hint.id = input.id + '-hint'; label.append(hint);
        return label;
    }
    const sections = [['basic', ui("Basic settings"), ''], ['radio', ui("Radio"), ui("Frequency, bandwidth, SF, CR, TX power")], ['location', ui("Location"), ui("Latitude and longitude")], ['advertisements', ui("Advertisements"), ui("Local and flood intervals")], ['routing', ui("Routing and regions"), ui("Forwarding, hop limits and regions")], ['access', ui("Access"), ui("Guest access and permissions")], ['owner', ui("Owner information"), ''], ['advanced', ui("Advanced"), ''], ['gps', 'GPS', ui("Requires GPS support")], ['bridge', ui("Bridge"), ui("Requires a bridge-enabled firmware build")]];
    function canPickLocation() { return !busy && admin && !!session && values.has('lat') && values.has('lon'); }
    function buildConfig() {
        const root = $('repeater-config'); root.replaceChildren();
        for (const [section, title, subtitle] of sections) {
            const box = disclosure(title, subtitle); box.open = section === 'basic';
            const form = node('form'), fields = Object.keys(schema).filter(field => schema[field].section === section), grid = node('div', undefined, 'repeater-fields');
            fields.forEach(field => grid.append(makeField(field, schema[field]))); form.append(grid);
            const toolbar = node('div', undefined, 'repeater-toolbar');
            toolbar.append(button(ui("Read"), () => run(() => readSection(fields)))); const save = node('button', ui("Save section")); save.type = 'submit'; toolbar.append(save); form.append(toolbar);
            form.addEventListener('submit', event => { event.preventDefault(); if (form.reportValidity()) run(() => saveSection(fields)); });
            box.append(form);
            if (section === 'location') {
                const choose = button(ui("Choose on map"), () => {
                    if (!canPickLocation()) return;
                    window.MeshcoreStationRepeaterLocation.open({current: [values.get('lat'), values.get('lon')], draft: [inputs.get('lat').value, inputs.get('lon').value], canEdit: canPickLocation,
                        report: message, apply: point => { inputs.get('lat').value = point[0].toFixed(6); inputs.get('lon').value = point[1].toFixed(6); message(ui("Position applied to the fields. Click Save section to update the repeater.")); }});
                });
                choose.id = 'repeater-choose-map'; form.insertBefore(choose, grid);
            }
            if (section === 'routing') buildRegions(box);
            if (section === 'access') buildPermissions(box);
            root.append(box);
        }
        const actions = node('section', undefined, 'repeater-section'); actions.append(node('h3', ui("Actions")));
        const toolbar = node('div', undefined, 'repeater-action-buttons');
        for (const [name, title] of [['advert', ui("Send advert")], ['clock_sync', ui("Sync clock")], ['reboot', ui("Reboot repeater")]]) toolbar.append(button(title, () => {
            if (!window.confirm(ui("{0} on {1}?", title, contact.name))) return;
            run(async () => { message(title + '…'); const result = await request({action: 'action', name, confirm: true}); message(uiError(result.message)); });
        }, name === 'reboot' ? 'repeater-danger' : ''));
        actions.append(toolbar); root.append(actions, node('p', ui("Available settings depend on firmware. Read values before editing. Sections are saved separately."), 'muted'));
    }
    async function readSection(fields) {
        if (fields.some(field => schema[field].kind !== 'password' && values.has(field) && fieldValue(field) !== values.get(field)) && !window.confirm(ui("Discard unsaved edits in this section and read current values?"))) return;
        const failures = [];
        for (const field of fields) {
            if (schema[field].kind === 'password') continue;
            message(ui("Reading ") + ui(schema[field].label) + '…');
            try {
                const result = await request({action: 'read', field}); setValue(field, result.value);
                $(inputs.get(field).id + '-hint').textContent = ui("Read from repeater.");
            } catch (error) { values.delete(field); $(inputs.get(field).id + '-hint').textContent = uiError(error.message); failures.push(ui(schema[field].label) + ': ' + uiError(error.message)); if (!session || /timed out|timeout|two minutes|Administrator/i.test(error.message)) break; }
        }
        message(failures.length ? failures.join('\n') : ui("Section read from repeater."), failures.length > 0);
    }
    async function saveSection(fields) {
        const changed = fields.filter(field => schema[field].kind === 'password' ? fieldValue(field) !== '' : values.has(field) && fieldValue(field) !== values.get(field));
        if (!changed.length) { message(ui("No changes to save.")); return; }
        const review = changed.map(field => ui(schema[field].label) + ': ' + (schema[field].kind === 'password' ? ui("(new password)") : fieldValue(field))).join('\n');
        if (!window.confirm(ui("Save to {0}?\n\n{1}{2}", contact.name, review, changed.includes('radio') ? ui("\n\nRadio changes may require a reboot and can affect connectivity.") : ''))) return;
        const saved = []; let reboot = false;
        for (const field of changed) {
            message(ui("Saving ") + ui(schema[field].label) + '…');
            const value = fieldValue(field), expected = values.get(field);
            // Do not keep a submitted password in the form, including on failure.
            if (schema[field].kind === 'password') inputs.get(field).value = '';
            try {
                const result = await request({action: 'write', field, value, expected: schema[field].kind === 'textarea' ? expected?.replaceAll('\n', '|') : expected, confirm: true});
                if (schema[field].kind !== 'password') setValue(field, result.value);
                saved.push(ui(schema[field].label)); reboot ||= result.reboot_required;
                $(inputs.get(field).id + '-hint').textContent = uiError(result.message);
            } catch (error) {
                if (schema[field].kind !== 'password') values.delete(field);
                message(ui("{0}{1}: {2} Remaining fields were not sent. Read this section before retrying.", saved.length ? ui("Confirmed: ") + saved.join(', ') + '. ' : '', ui(schema[field].label), uiError(error.message)), true); return;
            }
        }
        message(ui("Confirmed: ") + saved.join(', ') + '.' + (reboot ? ui(" Reboot required to apply radio settings.") : ''));
    }
    function buildRegions(box) {
        const section = node('div', undefined, 'repeater-subsection'), output = node('pre', ui("Regions have not been read."), 'repeater-data');
        section.append(node('h4', ui("Regions")), button(ui("Read regions"), () => run(async () => { const result = await request({action: 'regions_read'}); output.textContent = result.data; message(ui("Region response received.")); })), output);
        const form = node('form'), name = node('input'), parent = node('input'), operation = node('select');
        name.placeholder = ui("Region name, e.g. #Europe"); name.required = true; name.setAttribute('aria-label', ui("Region name")); parent.placeholder = ui("Parent region (default *)"); parent.setAttribute('aria-label', ui("Parent region"));
        for (const [value, label] of [['put', ui("Add / update parent")], ['remove', ui("Remove")], ['allowf', ui("Allow flooding")], ['denyf', ui("Block flooding")], ['home', ui("Set home")], ['default', ui("Set default scope")]]) { const option = node('option', label); option.value = value; operation.append(option); }
        operation.setAttribute('aria-label', ui("Region operation")); form.append(name, parent, operation); const apply = node('button', ui("Apply region change")); apply.type = 'submit'; form.append(apply);
        form.addEventListener('submit', event => { event.preventDefault(); if (!form.reportValidity() || !window.confirm(ui("{0}: {1} on {2}?", operation.selectedOptions[0].textContent, name.value, contact.name))) return; run(async () => { const result = await request({action: 'region', verb: operation.value, name: name.value, parent: parent.value, confirm: true}); message(uiError(result.message)); }); });
        section.append(form, node('p', ui("These are the repeater’s forwarding regions. Names, including any # prefix, are sent exactly as entered. Long region lists may be truncated by firmware."), 'muted')); box.append(section);
    }
    function buildPermissions(box) {
        const section = node('div', undefined, 'repeater-subsection'), output = node('div'); section.append(node('h4', ui("Companion permissions")));
        section.append(button(ui("Read permissions"), () => run(async () => { const result = await request({action: 'acl'}); output.replaceChildren(table([ui("Public key prefix"), ui("Permission")], result.data.map(row => [row.key, row.perm]))); message(ui("Permissions received.")); })), output);
        const form = node('form'), key = node('input'), permission = node('select'); key.placeholder = ui("Full companion public key"); key.pattern = '[a-fA-F0-9]{64}'; key.required = true; key.setAttribute('aria-label', ui("Companion public key"));
        [ui("Guest (0)"), ui("Read-only (1)"), ui("Read-write (2)"), ui("Admin (3)")].forEach((text, i) => { const option = node('option', text); option.value = String(i); permission.append(option); }); permission.setAttribute('aria-label', ui("Permission"));
        const save = node('button', ui("Apply permission")); save.type = 'submit'; form.append(key, permission, save);
        form.addEventListener('submit', event => { event.preventDefault(); if (!form.reportValidity() || !window.confirm(ui("Set {0} for {1}? Changing your companion’s permission may end management access.", permission.selectedOptions[0].textContent, key.value))) return; run(async () => { const result = await request({action: 'permission', target: key.value, permission: permission.value, confirm: true}); message(uiError(result.message)); }); });
        section.append(form); box.append(section);
    }
})();
