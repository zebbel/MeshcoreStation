(() => {
    let dialog, snapshot = null, busy = false, wantedKey = '', timer = null, dirty = false, channelsCache = [], templateValid = false, previewTimer, previewSerial = 0;
    const el = id => document.getElementById(id);
    const node = (tag, text) => { const n = document.createElement(tag); n.textContent = text; return n; };
    function message(text, bad = false) { el('voltage-message').textContent = text; el('voltage-message').classList.toggle('voltage-error', bad); }
    function controls() {
        dialog.querySelectorAll('button,input,select,textarea').forEach(n => n.disabled = busy);
        el('voltage-save').disabled = busy || !snapshot || !templateValid;
        el('voltage-read').disabled = busy || !snapshot || dirty || !snapshot.config.public_key;
    }
    async function request(body) {
        const options = {cache: 'no-store', headers: {'X-Meshcore-Control': '1'}};
        if (body) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
        const q = new URLSearchParams({days: el('voltage-days').value});
        if (wantedKey) q.set('public_key', wantedKey);
        const response = await fetch('/api/bot/voltage?' + q, options);
        let result;
        try { result = await response.json(); } catch { throw new Error('Unreadable response. Check the dashboard logs and refresh.'); }
        if (!response.ok || !result.ok) throw new Error(result.error || 'Voltage request failed.');
        return result;
    }
    function previewTemplate() {
        clearTimeout(previewTimer);const serial=++previewSerial;templateValid=false;controls();
        el('voltage-template-error').textContent='Checking template…';
        previewTimer=setTimeout(async()=>{
            try{
                const response=await fetch('/api/battery-report-preview',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},body:JSON.stringify({template:el('voltage-template').value})});
                const data=await response.json();if(serial!==previewSerial)return;
                if(!response.ok||!data.ok)throw Error(data.error||'Preview unavailable.');
                el('voltage-template-preview').textContent=data.preview;
                el('voltage-template-error').textContent='';templateValid=true;
            }catch(error){if(serial!==previewSerial)return;el('voltage-template-error').textContent=error.message;el('voltage-template-preview').textContent='Preview unavailable';}
            finally{if(serial===previewSerial)controls();}
        },250);
    }
    function templateEditor(data) {
        el('voltage-template').value=data.config.report_template||data.report_default;
        const box=el('voltage-placeholders');box.replaceChildren();
        for(const item of data.report_placeholders||[]){
            const token='{'+item.name+'}',chip=node('button',token);chip.type='button';chip.title=item.description;
            chip.onclick=()=>{const field=el('voltage-template');field.setRangeText(token,field.selectionStart,field.selectionEnd,'end');field.focus();dirty=true;previewTemplate();};box.append(chip);
        }
        previewTemplate();
    }
    function date(stamp, zone) { return window.meshcorestationFormatDate(stamp,zone,{seconds:false}); }
    function chart(samples, zone, days) {
        window.MeshcoreStationBattery.chart(el('voltage-chart'), el('voltage-chart-note'), samples, zone, days, snapshot.server_time);
    }
    function candidates(data) {
        const select = el('voltage-repeater'); select.replaceChildren(new Option('Choose a repeater…', ''));
        for (const r of data.repeaters) select.append(new Option(`${r.name || '(unnamed)'} · ${r.public_key.slice(0,12)}`, r.public_key));
        select.value = wantedKey || data.config.public_key;
        const list = el('voltage-repeaters'); list.replaceChildren();
        for (const r of data.repeaters) {
            const row = document.createElement('li'), name = node('span', `${r.name || '(unnamed)'} · ${r.public_key.slice(0,12)}`), b=node('button','Select');
            name.title=r.public_key; b.type='button'; b.addEventListener('click',()=>choose(r.public_key)); row.dataset.name=`${r.name} ${r.public_key}`.toLowerCase(); row.append(name,b); list.append(row);
        }
        filter();
    }
    function filter() { const q=el('voltage-search').value.trim().toLowerCase(); el('voltage-repeaters').querySelectorAll('li').forEach(n=>n.hidden=!n.dataset.name.includes(q)); }
    function reportDestinations(data) {
        const select = el('voltage-target'), selected = data.config.report_target || 'bot';
        select.replaceChildren(new Option('Follow bot chat / room', 'bot'));
        for (const chat of channelsCache.filter(c => c.type === 'private'))
            select.append(new Option('Chat: ' + chat.name + ' (slot ' + chat.index + ')', 'channel:' + chat.name));
        for (const room of data.rooms || [])
            if (room.enabled) select.append(new Option('Room: ' + room.name, 'room:' + room.id));
        if (![...select.options].some(option => option.value === selected))
            select.append(new Option('Unavailable: ' + selected, selected));
        select.value = selected;
    }
    async function refreshChannels() {
        try {
            const response = await fetch('/api/companion/channels', {cache:'no-store',headers:{'X-Meshcore-Control':'1'}});
            const data = await response.json();
            if (response.ok && data.ok && Array.isArray(data.channels)) channelsCache = data.channels;
        } catch (_) { /* Keep selected target visible when radio is offline. */ }
    }
    function render(data, form) {
        if (!form && snapshot) {
            if (dirty) data.config = snapshot.config;
            else if (data.config.revision !== snapshot.config.revision) form = true;
        }
        snapshot = data;
        if (form) {
            candidates(data);
            reportDestinations(data);
            const c=data.config;
            el('voltage-enabled').checked=c.enabled; el('voltage-reports').checked=c.reports_enabled;
            el('voltage-interval').value=c.interval_minutes; el('voltage-lpp').value=c.voltage_channel;
            el('voltage-time1').value=c.report_time_1; el('voltage-time2').value=c.report_time_2; el('voltage-zone').value=c.timezone;
            templateEditor(data);
            dirty = !!wantedKey && wantedKey!==c.public_key;
        }
        const latest=data.latest;
        el('voltage-latest').textContent=latest ? `${latest.voltage===null?'Reading failed':window.MeshcoreStationBattery.reading(latest.voltage)} · ${date(latest.sampled_at,data.config.timezone)}${latest.error?' · '+latest.error:''}` : 'No readings yet.';
        const worker=data.worker, active=worker && worker.state!=='stopped' && data.server_time-worker.heartbeat<150;
        const target = data.config.report_target || 'bot';
        const room = (data.rooms || []).find(r => 'room:' + r.id === target);
        const destination = target === 'bot' ? 'bot chat / room' : target.startsWith('channel:') ? 'chat ' + target.slice(8) : room ? 'room ' + room.name : target;
        el('voltage-worker').textContent=`${active?'Bot monitor: '+worker.state:'Bot monitor offline'} · Reports to: ${destination}.`;
        el('voltage-chart-note').textContent=''; chart(data.samples,data.config.timezone,Number(el('voltage-days').value));
        const rows=el('voltage-recent'); rows.replaceChildren();
        for (const p of [...data.samples].slice(-10).reverse()) { const tr=document.createElement('tr'); for(const t of [date(p.sampled_at,data.config.timezone),p.voltage===null?'—':window.MeshcoreStationBattery.reading(p.voltage),p.error||'OK']) tr.append(node('td',t)); rows.append(tr); }
        const reports=el('voltage-report-log'); reports.replaceChildren();
        for (const r of data.reports) reports.append(node('li',`${date(r.attempted_at,data.config.timezone)} · ${r.status} · ${r.channel_name||'no channel'} · ${r.detail}`));
    }
    async function load(form = false, silent = false) {
        if (busy || (silent && dirty)) return;
        busy=true;controls();
        if (!silent) message('Loading voltage history…');
        try { if(form) await refreshChannels(); render(await request(),form); if (!silent) message(dirty?'Repeater selected. Save to use it for monitoring.':'History refreshed.'); }
        catch(error) { message(error.message,true); if(form) snapshot=null; }
        finally { busy=false;controls(); }
    }
    function choose(key) {
        if (dirty && !window.confirm('Discard unsaved settings and select another repeater?')) { el('voltage-repeater').value=wantedKey || snapshot?.config.public_key || ''; return; }
        wantedKey=key;dirty=false;load(true);
    }
    async function save(event) {
        event.preventDefault(); if(busy || !snapshot || !templateValid || !el('voltage-form').reportValidity()) return;
        const value={enabled:el('voltage-enabled').checked,public_key:el('voltage-repeater').value,interval_minutes:Number(el('voltage-interval').value),reports_enabled:el('voltage-reports').checked,report_time_1:el('voltage-time1').value,report_time_2:el('voltage-time2').value,timezone:el('voltage-zone').value.trim(),voltage_channel:Number(el('voltage-lpp').value),report_target:el('voltage-target').value,report_template:el('voltage-template').value};
        busy=true;controls();
        try { await request({operation:'save',expected_revision:snapshot.config.revision,value});wantedKey=value.public_key;dirty=false;message('Settings saved. The bot applies them automatically.'); }
        catch(error) { message(error.message+' Refresh before retrying.',true); return; }
        finally {busy=false;controls();}
        await load(true);
    }
    async function read() {
        if(busy || !snapshot || dirty) return;
        busy=true;controls();
        try {await request({operation:'sample',expected_revision:snapshot.config.revision});message('Reading requested. The bot will collect it shortly; a radio request can take about a minute.');}
        catch(error){message(error.message,true);}
        finally{busy=false;controls();}
    }
    function close() {if(!busy && (!dirty || window.confirm('Discard unsaved battery settings?'))) {dialog.close();clearInterval(timer);timer=null;clearTimeout(previewTimer);++previewSerial;} }
    function create() {
        dialog=document.createElement('dialog');dialog.id='voltage-dialog';dialog.setAttribute('aria-labelledby','voltage-title');
        dialog.innerHTML=`<div class="dialog-header"><h2 id="voltage-title">Repeater battery</h2><button type="button" id="voltage-close" aria-label="Close battery history">×</button></div>
        <p id="voltage-message" role="status" aria-live="polite"></p><p id="voltage-worker" class="muted"></p>
        <form id="voltage-form"><div class="voltage-fields">
        <div class="voltage-wide voltage-repeater-choice"><label>Repeater<select id="voltage-repeater"></select></label><button type="button" id="voltage-map">Select repeater on map</button></div>
        <fieldset class="voltage-wide voltage-group"><legend>Monitoring</legend><div class="voltage-fields">
        <label class="voltage-wide voltage-toggle"><input type="checkbox" id="voltage-enabled"> Enable monitoring</label>
        <label>Read every (minutes)<input id="voltage-interval" type="number" min="5" max="1440" required></label>
        <label>Voltage LPP channel<input id="voltage-lpp" type="number" min="1" max="255" required></label>
        </div></fieldset>
        <fieldset class="voltage-wide voltage-group"><legend>Daily reports</legend><div class="voltage-fields">
        <label class="voltage-wide voltage-toggle"><input type="checkbox" id="voltage-reports"> Send two daily reports</label>
        <label>First report<input id="voltage-time1" type="time" required></label><label>Second report<input id="voltage-time2" type="time" required></label>
        <label>Timezone<input id="voltage-zone" required placeholder="Europe/Berlin"></label><label>Send battery reports to<select id="voltage-target" required></select></label></div></fieldset></div>
        <section class="voltage-template-editor"><h3>Report message template</h3><label for="voltage-template">Message</label><textarea id="voltage-template" rows="3" maxlength="512" required></textarea><div id="voltage-placeholders" class="template-placeholders"></div><p class="muted">Click a placeholder to insert it at the cursor. Numeric formatting: {battery_voltage:.2f}. Uses the last successful reading; missing values show “unknown”. Longer reports are split into radio messages.</p><button type="button" id="voltage-template-default">Use default message</button><h4>Live preview · example reading</h4><pre id="voltage-template-preview"></pre><p id="voltage-template-error" role="status" class="voltage-error"></p></section>
        <p class="muted">Guest telemetry; no password. Reading adds the selected repeater to companion Contacts if it is missing. Channel 1 is the usual battery sensor; use the reported voltage channel if different. Save changes to switch monitoring. Reports may follow the bot or use a private chat or enabled room. Previous history is kept.</p>
        <div class="voltage-actions"><button id="voltage-save" type="submit">Save settings</button><button id="voltage-read" type="button">Read now</button><button id="voltage-refresh" type="button">Refresh</button></div></form>
        <details><summary>Select from repeater list</summary><input id="voltage-search" type="search" aria-label="Search repeaters" placeholder="Search name or public key"><ul id="voltage-repeaters"></ul></details>
        <h3 id="voltage-latest">No readings yet.</h3><label>Chart period <select id="voltage-days"><option value="1" selected>24 hours</option><option value="7">7 days</option><option value="30">30 days</option></select></label>
        <div id="voltage-chart"></div><p id="voltage-chart-note" class="muted"></p>
        <details><summary>Recent readings</summary><table><thead><tr><th>Time</th><th>Voltage</th><th>Result</th></tr></thead><tbody id="voltage-recent"></tbody></table></details>
        <details><summary>Recent report attempts</summary><ul id="voltage-report-log"></ul><p class="muted">Queued means accepted by the companion, not confirmed delivery. Missed report times have a 10-minute grace period; interrupted sends are not retried automatically.</p></details>`;
        window.meshcorestationPrepareDialog(dialog);
        document.body.append(dialog);
        el('voltage-template').addEventListener('input',previewTemplate);
        el('voltage-template-default').onclick=()=>{el('voltage-template').value=snapshot.report_default;dirty=true;previewTemplate();};
        el('voltage-close').addEventListener('click',close);dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
        el('voltage-form').addEventListener('submit',save);
        el('voltage-map').onclick=()=>pick(snapshot);
        el('voltage-form').addEventListener('input',e=>{if(e.target.id!=='voltage-repeater'){dirty=true;controls();}});
        el('voltage-repeater').addEventListener('change',()=>choose(el('voltage-repeater').value));
        el('voltage-search').addEventListener('input',filter);el('voltage-read').addEventListener('click',read);
        el('voltage-days').addEventListener('change',()=>load());
        el('voltage-refresh').addEventListener('click',()=>{if(!dirty||window.confirm('Discard unsaved changes and refresh?')){dirty=false;load(true);}});
    }
    function open(key='') {
        if(!dialog)create();if(dialog.open)return;
        wantedKey=key;dirty=false;snapshot=null;dialog.showModal();load(true);
        clearInterval(timer);timer=setInterval(()=>{if(dialog.open)load(false,true);},15000);
    }
    function pick(data) {
        if (!data) return;
        document.dispatchEvent(new CustomEvent('stats-picker-open', {detail: {repeaters:data.repeaters,selected:dialog?.open ? el('voltage-repeater').value : data.config.public_key,selectionEvent:'battery-picker-selected',title:'Select battery repeater'}}));
    }
    document.addEventListener('battery-picker-selected',event=>{if(dialog?.open)choose(event.detail);else open(event.detail);});
    document.addEventListener('click',async event=>{
        const button=event.target.closest('#select-voltage-repeater');if(!button)return;
        button.disabled=true;
        try {
            const response=await fetch('/api/bot/voltage?days=1',{cache:'no-store',headers:{'X-Meshcore-Control':'1'}});
            const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Could not load repeaters.');pick(data);
        } catch(error) {window.alert(error.message);} finally {button.disabled=false;}
    });
    document.addEventListener('meshcore-voltage-open',e=>{const key=e.detail?.public_key||'';if(dialog?.open&&key)choose(key);else open(key);});
    document.addEventListener('click',e=>{if(e.target.closest('#open-voltage'))open(window.meshcorestationSelectedRepeater||'');});
})();
