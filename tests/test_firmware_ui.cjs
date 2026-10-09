const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const dom = new JSDOM('<dialog id="companion-dialog" open><div class="companion-grid"></div></dialog>', {runScripts:'outside-only',url:'http://localhost/'});
const w = dom.window;
w.AbortSignal.timeout = () => undefined;
w.confirm = () => true;
let tick, checked = false, busy = false, installs = 0;
w.setInterval = cb => { tick = cb; return 1; };
w.fetch = async (url, options) => {
    assert.equal(options.headers['X-Meshcore-Control'], '1');
    const body = options.body ? JSON.parse(options.body) : {};
    if (body.action === 'check') checked = true;
    if (body.action === 'install') { installs++; assert.equal(body.release_id, 7); assert(body.confirm_heltec_v4); busy = true; }
    return {ok:true,json:async()=>({ok:true,ready:true,device:{ver:'test'},status:{busy,message:busy?'Flashing':'Ready',log:'<script>unsafe</script>'},releases:checked?[{id:7,name:'OLED',prerelease:true}]:[]})};
};
const settle = () => new Promise(r => setImmediate(r));
(async()=>{
    w.eval(fs.readFileSync('meshcorestation/web/assets/firmware.js','utf8'));
    await settle();
    const panel = w.document.querySelector('#firmware-panel');
    assert(panel.querySelector('.firmware-install').disabled);
    panel.querySelector('.firmware-check').click(); await settle();
    assert(!panel.querySelector('.firmware-install').disabled);
    assert(panel.querySelector('option').textContent.includes('prerelease'));
    panel.querySelector('.firmware-install').click(); await settle();
    assert.equal(installs,1);
    assert(panel.querySelector('.firmware-check').disabled);
    assert(!panel.querySelector('script'));
    busy=false; tick(); await settle();
    assert(!panel.querySelector('.firmware-install').disabled);
    dom.window.close(); console.log('Firmware UI passed');
})().catch(e=>{console.error(e);process.exit(1);});
