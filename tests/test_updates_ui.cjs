const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const dom = new JSDOM('<html><body><dialog id="companion-dialog"><div class="companion-grid"></div></dialog></body></html>', {runScripts:'outside-only', url:'http://localhost/'});
const w = dom.window;
w.AbortSignal.timeout = () => undefined;
w.confirm = () => true;
let phase = '', checked = false, installed = false, tick;
const requests = [];
w.setInterval = callback => { tick = callback; return 1; };
w.clearInterval = () => {};
w.fetch = async (url, options) => {
    const body = options.body ? JSON.parse(options.body) : null;
    requests.push(body);
    if (body?.action === 'check') checked = true;
    if (body?.action === 'install') { installed = true; phase = 'queued'; assert.equal(body.target, 'b'.repeat(40)); }
    return {ok:true, json:async()=>({ok:true,version:'2.1.0',revision:'a'.repeat(40), ready:true,
        check:checked ? {latest:'b'.repeat(40),available:true,latest_version:'2.2.0',checked_at:1,changes_url:'https://github.com/zebbel/MeshcoreStation/compare/a...b'} : {},
        status:{phase,message:phase ? 'Update '+phase : ''}})};
};
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
    w.eval(fs.readFileSync('meshcorestation/web/assets/updates.js', 'utf8'));
    await settle();
    const panel = w.document.querySelector('#update-panel');
    assert(panel);
    assert(panel.querySelector('.update-install').disabled);
    panel.querySelector('.update-check').click(); await settle();
    assert(!panel.querySelector('.update-install').disabled);
    assert(panel.querySelector('.update-latest').textContent.includes('2.2.0'));
    panel.querySelector('.update-install').click(); await settle();
    assert(installed);
    assert(panel.querySelector('.update-check').disabled);
    phase = 'complete'; await tick(); await settle();
    assert(!panel.querySelector('.update-reload').hidden);
    assert.equal(requests.filter(b => b?.action === 'install').length,1);
    dom.window.close();
    console.log('Updates UI check/install/poll/reconnect checks passed.');
})().catch(error => { console.error(error); process.exit(1); });
