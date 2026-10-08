/* Saved reply scopes live in SQLite and take effect without restarting the radio. */
(() => {
    let dialog, snapshot = null, original = null, busy = false, dirty = false;
    const el = id => document.getElementById(id);
    function message(text, bad = false) { el('scopes-message').textContent = text; el('scopes-message').classList.toggle('scopes-error', bad); }
    function controls() {
        dialog.querySelectorAll('button,input').forEach(n => n.disabled = busy);
        el('scope-save').disabled = busy || !snapshot;
        dialog.setAttribute('aria-busy', String(busy));
    }
    async function request(body) {
        const options = {headers: {'X-Meshcore-Control': '1'}};
        if (body) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
        const response = await fetch('/api/bot/scopes', options);
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'Scope request failed. Reload before retrying.');
        return result;
    }
    function reset() { original = null; dirty = false; el('scope-name').value = ''; el('scope-save').textContent = 'Add scope'; }
    function discard() { return !dirty || window.confirm('Discard unsaved scope changes?'); }
    function render() {
        const list = el('scopes-list'); list.replaceChildren();
        for (const scope of snapshot.scopes) {
            const row = document.createElement('li'), label = document.createElement('div'), name = document.createElement('strong'), key = document.createElement('small');
            name.textContent = scope.name; key.textContent = scope.scope_key; label.append(name, key); row.append(label);
            const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = 'Edit';
            edit.addEventListener('click', () => { if (!discard()) return; original = scope.name; el('scope-name').value = scope.name; el('scope-save').textContent = 'Save scope'; dirty = false; el('scope-name').focus(); });
            const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove';
            remove.addEventListener('click', () => removeScope(scope)); row.append(edit, remove); list.append(row);
        }
        el('scopes-count').textContent = snapshot.scopes.length ? `${snapshot.scopes.length} saved scopes` : 'No saved scopes yet.';
        controls();
    }
    async function load() {
        if (busy || !discard()) return;
        busy = true; controls(); message('Loading scopes…');
        try { snapshot = await request(); reset(); render(); message('Scopes loaded.'); }
        catch (error) { snapshot = null; message(error.message, true); }
        finally { busy = false; controls(); }
    }
    async function save(event) {
        event.preventDefault(); if (busy || !snapshot || !el('scope-form').reportValidity()) return;
        const name = el('scope-name').value.trim().replace(/^#/, '');
        if (original !== null && name !== original && !window.confirm(`Rename ${original} to ${name}? The scope key will change to match the new name.`)) return;
        busy = true; controls();
        try { snapshot = await request({operation: original === null ? 'add' : 'edit', original_name: original, name, expected_revision: snapshot.revision}); reset(); render(); message('Scope saved.'); }
        catch (error) { message(error.message, true); }
        finally { busy = false; controls(); }
    }
    async function removeScope(scope) {
        if (busy || !discard() || !window.confirm(`Remove ${scope.name}? MeshcoreStation will no longer recognize this saved reply scope.`)) return;
        busy = true; controls();
        try { snapshot = await request({operation: 'delete', original_name: scope.name, confirm_delete: true, expected_revision: snapshot.revision}); reset(); render(); message('Scope removed.'); }
        catch (error) { message(error.message, true); }
        finally { busy = false; controls(); }
    }
    function create(parent) {
        dialog = document.createElement('section'); dialog.id = 'scope-settings'; dialog.className = 'companion-section'; dialog.setAttribute('aria-labelledby', 'scopes-title');
        dialog.innerHTML = `<h3 id="scopes-title">Scopes</h3>
        <p class="muted">Saved region scopes let MeshcoreStation recognize scoped messages and reply in the same scope. Keys are generated from the name. Renaming changes the key. The companion’s default transmit scope is configured separately in Network settings.</p>
        <p id="scopes-message" role="status" aria-live="polite"></p><button type="button" id="scopes-reload">Reload</button>
        <form id="scope-form"><label for="scope-name">Scope name</label><input id="scope-name" maxlength="31" pattern="#?[A-Za-z0-9_-]{1,30}" required autocomplete="off" placeholder="Region name"><div class="scope-actions"><button type="submit" id="scope-save">Add scope</button><button type="button" id="scope-cancel">Clear / cancel edit</button></div></form>
        <p id="scopes-count" class="muted"></p><ul id="scopes-list"></ul>`;
        const network=parent.querySelector('#network-settings');
        if(network) network.after(dialog); else parent.querySelector('.companion-grid').append(dialog);
        parent.addEventListener('settings-before-close', event => { if (busy || !discard()) event.preventDefault(); });
        parent.addEventListener('close', reset);
        new MutationObserver(() => { if(parent.open) load(); }).observe(parent, {attributes:true, attributeFilter:['open']});
        el('scopes-reload').addEventListener('click', load); el('scope-form').addEventListener('submit', save);
        el('scope-name').addEventListener('input', () => dirty = true);
        el('scope-cancel').addEventListener('click', () => { if (discard()) reset(); });
    }
    function attach() {
        const parent=el('companion-dialog');
        if(!parent || dialog)return;
        create(parent);
        if(parent.open)load();
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});
    attach();
})();
