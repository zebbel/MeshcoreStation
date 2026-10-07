(() => {
    let dialog, snapshot = null, busy = false, wantedKey = '', timer = null, dirty = false;
    const el = id => document.getElementById(id);
    const node = (tag, text) => { const n = document.createElement(tag); n.textContent = text; return n; };
    function message(text, bad = false) { el('voltage-message').textContent = text; el('voltage-message').classList.toggle('voltage-error', bad); }
    function controls() {
        dialog.querySelectorAll('button,input,select').forEach(n => n.disabled = busy);
        el('voltage-save').disabled = busy || !snapshot;
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
    function date(stamp, zone) { return new Date(stamp * 1000).toLocaleString(undefined, {timeZone: zone, dateStyle: 'short', timeStyle: 'short'}); }
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
    function render(data, form) {
        if (!form && snapshot) {
            if (dirty) data.config = snapshot.config;
            else if (data.config.revision !== snapshot.config.revision) form = true;
        }
        snapshot = data;
        if (form) {
            candidates(data);
            const c=data.config;
            el('voltage-enabled').checked=c.enabled; el('voltage-reports').checked=c.reports_enabled;
            el('voltage-interval').value=c.interval_minutes; el('voltage-lpp').value=c.voltage_channel;
            el('voltage-time1').value=c.report_time_1; el('voltage-time2').value=c.report_time_2; el('voltage-zone').value=c.timezone;
            dirty = !!wantedKey && wantedKey!==c.public_key;
        }
        const latest=data.latest;
        el('voltage-latest').textContent=latest ? `${latest.voltage===null?'Reading failed':window.MeshcoreStationBattery.reading(latest.voltage)} · ${date(latest.sampled_at,data.config.timezone)}${latest.error?' · '+latest.error:''}` : 'No readings yet.';
        const worker=data.worker, active=worker && worker.state!=='stopped' && data.server_time-worker.heartbeat<150;
        el('voltage-worker').textContent=`${active?'Bot monitor: '+worker.state:'Bot monitor offline'} · Reports follow bot channel: ${data.bot_channel || '(none selected)'}. Private channels only.`;
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
        try { render(await request(),form); if (!silent) message(dirty?'Repeater selected. Save to use it for monitoring.':'History refreshed.'); }
        catch(error) { message(error.message,true); if(form) snapshot=null; }
        finally { busy=false;controls(); }
    }
    function choose(key) {
        if (dirty && !window.confirm('Discard unsaved settings and select another repeater?')) { el('voltage-repeater').value=wantedKey || snapshot?.config.public_key || ''; return; }
        wantedKey=key;dirty=false;load(true);
    }
    async function save(event) {
        event.preventDefault(); if(busy || !snapshot || !el('voltage-form').reportValidity()) return;
        const value={enabled:el('voltage-enabled').checked,public_key:el('voltage-repeater').value,interval_minutes:Number(el('voltage-interval').value),reports_enabled:el('voltage-reports').checked,report_time_1:el('voltage-time1').value,report_time_2:el('voltage-time2').value,timezone:el('voltage-zone').value.trim(),voltage_channel:Number(el('voltage-lpp').value)};
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
    function close() {if(!busy && (!dirty || window.confirm('Discard unsaved battery settings?'))) {dialog.close();clearInterval(timer);timer=null;} }
    function create() {
        dialog=document.createElement('dialog');dialog.id='voltage-dialog';dialog.setAttribute('aria-labelledby','voltage-title');
        dialog.innerHTML=`<div class="dialog-header"><h2 id="voltage-title">Repeater battery</h2><button type="button" id="voltage-close" aria-label="Close battery history">×</button></div>
        <p id="voltage-message" role="status" aria-live="polite"></p><p id="voltage-worker" class="muted"></p>
        <form id="voltage-form"><div class="voltage-fields">
        <label class="voltage-wide">Repeater<select id="voltage-repeater"></select></label>
        <label><input type="checkbox" id="voltage-enabled"> Enable monitoring</label><label><input type="checkbox" id="voltage-reports"> Send two daily reports</label>
        <label>Read every (minutes)<input id="voltage-interval" type="number" min="5" max="1440" required></label>
        <label>Voltage LPP channel<input id="voltage-lpp" type="number" min="1" max="255" required></label>
        <label>First report<input id="voltage-time1" type="time" required></label><label>Second report<input id="voltage-time2" type="time" required></label>
        <label class="voltage-wide">Timezone<input id="voltage-zone" required placeholder="Europe/Berlin"></label></div>
        <p class="muted">Guest telemetry; no password. Reading adds the selected repeater to companion Contacts if it is missing. Channel 1 is the usual battery sensor; use the reported voltage channel if different. Save changes to switch monitoring. Previous history is kept.</p>
        <div class="voltage-actions"><button id="voltage-save" type="submit">Save settings</button><button id="voltage-read" type="button">Read now</button><button id="voltage-refresh" type="button">Refresh</button></div></form>
        <details><summary>Select from repeater list</summary><input id="voltage-search" type="search" aria-label="Search repeaters" placeholder="Search name or public key"><ul id="voltage-repeaters"></ul></details>
        <h3 id="voltage-latest">No readings yet.</h3><label>Chart period <select id="voltage-days"><option value="1" selected>24 hours</option><option value="7">7 days</option><option value="30">30 days</option></select></label>
        <div id="voltage-chart"></div><p id="voltage-chart-note" class="muted"></p>
        <details><summary>Recent readings</summary><table><thead><tr><th>Time</th><th>Voltage</th><th>Result</th></tr></thead><tbody id="voltage-recent"></tbody></table></details>
        <details><summary>Recent report attempts</summary><ul id="voltage-report-log"></ul><p class="muted">Queued means accepted by the companion, not confirmed delivery. Missed report times have a 10-minute grace period; interrupted sends are not retried automatically.</p></details>`;
        window.meshcorestationPrepareDialog(dialog);
        document.body.append(dialog);
        el('voltage-close').addEventListener('click',close);dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
        el('voltage-form').addEventListener('submit',save);
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
    document.addEventListener('meshcore-voltage-open',e=>open(e.detail?.public_key||''));
    document.addEventListener('click',e=>{if(e.target.closest('#open-voltage'))open();});
})();
