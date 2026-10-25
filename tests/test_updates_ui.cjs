const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const dom = new JSDOM('<html><body><dialog id="companion-dialog"><div class="dialog-header"></div><div class="dialog-body"><details id="companion-settings-disclosure"><div class="companion-grid"></div></details></div></dialog></body></html>', {runScripts:'outside-only', url:'http://localhost/'});
const w = dom.window;
w.AbortSignal.timeout = () => undefined;
w.confirm = () => true;
w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
let checkedBranch = 'main';
let phase = '', checked = false, installed = false, tick;
const requests = [];
w.setInterval = callback => { tick = callback; return 1; };
w.clearInterval = () => {};
w.fetch = async (url, options) => {
    const body = options.body ? JSON.parse(options.body) : null;
    requests.push(body);
    if (body?.action === 'branches') return {ok:true,json:async()=>({ok:true,branches:{main:'main','feature/v3':'feature/v3','feature/room-server':'feature/room-server','custom/new-branch':'custom/new-branch'}})};
    if (body?.action === 'check') { checked = true; checkedBranch = body.branch; }
    if (body?.action === 'install') { installed = true; phase = 'queued'; assert.equal(body.target, 'b'.repeat(40)); assert.equal(body.branch, 'feature/room-server'); }
    return {ok:true, json:async()=>({ok:true,branch:'main',version:'2.1.0',revision:'a'.repeat(40), ready:true,
        check:checked ? {branch:checkedBranch,latest:'b'.repeat(40),available:true,latest_version:'2.2.0',checked_at:1,changes_url:'https://github.com/zebbel/MeshcoreStation/compare/a...b'} : {},
        status:{phase,message:phase ? 'Update '+phase : ''}})};
};
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
    w.eval(fs.readFileSync('meshcorestation/web/assets/aa_display.js','utf8'));
w.eval(fs.readFileSync('meshcorestation/web/assets/updates.js', 'utf8'));
    await settle();
    const panel = w.document.querySelector('#update-panel');
    assert.equal(panel.parentElement.className, 'dialog-body', 'Updates must share the scrollable settings body');
    assert(!panel.closest('details'), 'Updates must remain outside collapsed companion settings');
    assert(panel);
    assert.equal(panel.querySelector('.update-branches'),null);
    assert(panel.querySelector('.update-install').disabled);
    const refreshes=requests.filter(r=>r?.action==='branches').length;
    panel.querySelector('.update-check').click(); await settle();
    assert.equal(requests.filter(r=>r?.action==='branches').length,refreshes+1);
    assert(!panel.querySelector('.update-install').disabled);
    assert(panel.querySelector('.update-latest').textContent.includes('2.2.0'));
    const select = panel.querySelector('.update-branch');
    assert([...select.options].some(o=>o.value==='custom/new-branch'));
    select.value = 'feature/v3'; select.dispatchEvent(new w.Event('change'));
    assert(panel.querySelector('.update-install').disabled);
    panel.querySelector('.update-check').click(); await settle();
    assert.equal(checkedBranch, 'feature/v3');
    assert(!panel.querySelector('.update-install').disabled);
    select.value = 'feature/room-server'; select.dispatchEvent(new w.Event('change'));
    assert(panel.querySelector('.update-install').disabled);
    panel.querySelector('.update-check').click(); await settle();
    assert.equal(checkedBranch, 'feature/room-server');
    assert(!panel.querySelector('.update-install').disabled);
    panel.querySelector('.update-install').click(); await settle();
    assert(installed);
    assert(panel.querySelector('.update-check').disabled);
    phase = 'complete'; await tick(); await settle();
    assert(!panel.querySelector('.update-reload').hidden);
    assert.equal(requests.filter(b => b?.action === 'install').length,1);
    w.meshcorestationOpenInstalledUpdate({ok:true,branch:'main',version:'4.3.3',revision:'a'.repeat(40),ready:true,check:{branch:'main',latest:'b'.repeat(40),available:true,latest_version:'4.3.4'},status:{}});
    assert.equal(panel.querySelector('.update-branch').value,'main','footer handoff restores installed branch after another branch was selected');
    w.confirm=()=>false;panel.querySelector('.update-install').click();await settle();
    assert.equal(requests.filter(b=>b?.action==='install').length,1,'footer handoff preserves explicit installation confirmation');
    dom.window.close();
    console.log('Updates UI check/install/poll/reconnect checks passed.');
})().catch(error => { console.error(error); process.exit(1); });
