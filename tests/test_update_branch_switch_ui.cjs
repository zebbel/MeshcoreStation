const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');

async function verify(installed, other) {
    const dom = new JSDOM('<dialog id="station-settings-dialog"></dialog>', {
        url: 'http://localhost/', runScripts: 'outside-only',
    });
    const { window: w } = dom;
    const calls = [];
    let checked = {}, status = {};
    w.meshcorestationFormatDate = () => 'today';
    w.confirm = () => false;
    w.fetch = async (url, options) => {
        assert.equal(url, '/api/update');
        const request = options.body && JSON.parse(options.body);
        if (request) calls.push(request);
        if (request?.action === 'branches') return response({ branches: { V5: 'V5', V6: 'V6' } });
        if (request?.action === 'check') checked = { branch: request.branch, latest: 'b'.repeat(40), available: true, latest_version: 'example' };
        if (request?.action === 'install') status = { phase: 'queued' };
        return response({ branch: installed, version: 'example', revision: 'a'.repeat(40), ready: true, check: checked, status });
    };
    const response = data => ({ ok: true, json: async () => ({ ok: true, ...data }) });
    const settle = () => new Promise(resolve => setImmediate(resolve));
    try {
        w.eval(fs.readFileSync('meshcorestation/web/assets/updates.js', 'utf8'));
        await settle();
        const select = w.document.querySelector('.update-branch');
        const install = w.document.querySelector('.update-install');
        assert.deepEqual([...select.options].map(option => option.value), ['V5', 'V6']);
        assert.equal(select.value, installed);
        select.value = other;
        select.dispatchEvent(new w.Event('change'));
        assert(install.disabled);
        w.document.querySelector('.update-check').click();
        await settle();
        assert.equal(install.textContent, 'Switch to ' + other);
        assert(!install.disabled);
        install.click();
        assert(!calls.some(call => call.action === 'install'));
        w.confirm = () => true;
        install.click();
        await settle();
        assert.deepEqual(calls.at(-1), { action: 'install', branch: other, target: 'b'.repeat(40) });
    } finally {
        w.close();
    }
}

(async () => {
    await verify('V5', 'V6');
    await verify('V6', 'V5');
    console.log('Dashboard checks and confirms branch switching in both directions.');
})().catch(error => { console.error(error); process.exitCode = 1; });
