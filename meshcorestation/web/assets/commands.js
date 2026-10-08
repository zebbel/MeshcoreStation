/* Edit a local draft; only Save changes writes SQLite. Previews never use the radio. */
(() => {
    let dialog, editor, snapshot, draft = [], currentId = null, busy = false, catalog = [], previewTimer, previewSequence = 0, activeTemplate = 'command-reply';
    const actionLabels = {reply: 'Reply', position: 'Update sender position', scope: 'Add scope'};
    const $ = id => document.getElementById(id), copy = value => JSON.parse(JSON.stringify(value));
    const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
    function button(text, action, cls) { const n = node('button', text, cls); n.type = 'button'; n.addEventListener('click', action); return n; }
    function message(text, error = false) { $('commands-message').textContent = text; $('commands-message').classList.toggle('commands-error', error); }
    function dirty() { return snapshot && JSON.stringify(draft) !== JSON.stringify(snapshot.commands); }
    function controls() {
        for (const root of [dialog, editor]) if (root) root.querySelectorAll('button,input,textarea,select').forEach(n => n.disabled = busy);
        if ($('command-action')) $('command-action').disabled = busy || currentId === 'help';
        $('commands-save').disabled = busy || !snapshot || !dirty();
        $('commands-add').disabled = busy || !snapshot || draft.length >= (snapshot.max_commands || 24);
        $('commands-dirty').textContent = dirty() ? 'Unsaved changes' : 'All changes saved';
        dialog.setAttribute('aria-busy', String(busy));
    }
    async function request(body) {
        const options = {cache: 'no-store', headers: {'X-Meshcore-Control': '1'}};
        if (body) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
        const response = await fetch('/api/bot/commands', options);
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'Command request failed. Reload before retrying.');
        return result;
    }
    function formCommand() {
        const previous = draft.find(c => c.id === currentId);
        return {...previous, id: currentId, trigger: $('command-trigger').value.trim().toLowerCase(), help: $('command-help').value, reply: $('command-reply').value, action: $('command-action').value, failure_reply: $('command-action').value === 'reply' ? '@{sender_name} | {result}' : $('command-failure').value};
    }
    function formDirty() { return JSON.stringify(formCommand()) !== JSON.stringify(draft.find(c => c.id === currentId) || {id: currentId, trigger: '', help: '', reply: '', action: 'reply', failure_reply: '@{sender_name} | {result}'}); }
    function candidateList() {
        const command = formCommand(), result = copy(draft), index = result.findIndex(c => c.id === currentId);
        if (index === -1) result.push(command); else result[index] = command;
        return result;
    }
    function schedulePreview() {
        clearTimeout(previewTimer); ++previewSequence;
        $('command-preview').textContent = 'Updating preview…';
        previewTimer = setTimeout(() => preview(true), 250);
    }
    async function preview(editing = false) {
        const sequence = ++previewSequence;
        try {
            const result = await request({operation: 'preview', commands: editing ? candidateList() : draft, selected_id: editing ? currentId : 'help'});
            if (sequence !== previewSequence) return;
            if (editing) { $('command-preview').textContent = result.reply; $('command-failure-preview').textContent = result.failure_reply || '';  $('command-editor-message').textContent = ''; }
            else $('commands-help-preview').textContent = result.help_reply;
        } catch (error) {
            if (sequence !== previewSequence) return;
            if (editing) { $('command-preview').textContent = 'Preview unavailable'; $('command-editor-message').textContent = error.message; }
            else $('commands-help-preview').textContent = error.message;
        }
    }
    function render() {
        const list = $('commands-list'); list.replaceChildren();
        for (const command of draft) {
            const row = node('li', undefined, 'command-row'), name = node('strong', command.trigger, 'command-name'), detail = node('div', undefined, 'command-description');
            if (command.id === 'help') detail.append(node('span', '🔒 Required', 'command-badge'));
            detail.append(node('p', command.help), node('code', command.reply));
            detail.append(node('small', 'Action: ' + actionLabels[command.action], 'muted'));
            if (command.action !== 'reply') detail.append(node('p', 'On failure:'), node('code', command.failure_reply));
            const actions = node('div', undefined, 'command-actions'); actions.append(button('Edit', () => edit(command.id)));
            if (command.id !== 'help') actions.append(button('Delete', () => {
                if (busy || !window.confirm(`Delete ${command.trigger}? It will stop responding after you save changes.`)) return;
                draft = draft.filter(c => c.id !== command.id); render(); preview();
            }, 'command-delete'));
            row.append(name, detail, actions); list.append(row);
        }
        controls();
    }
    async function load() {
        if (busy || (dirty() && !window.confirm('Discard unsaved command changes and reload?'))) return;
        busy = true; controls(); message('Loading commands…');
        try { snapshot = await request(); catalog = snapshot.placeholders; draft = copy(snapshot.commands); render(); message(''); await preview(); }
        catch (error) { message(error.message, true); }
        finally { busy = false; controls(); }
    }
    async function save() {
        if (busy || !snapshot || !dirty()) return;
        busy = true; controls(); message('Saving commands…');
        try {
            const result = await request({operation: 'save', commands: draft, expected_revision: snapshot.revision});
            snapshot = {...snapshot, ...result}; draft = copy(result.commands); render(); message('Commands saved. Changes are active immediately.'); await preview();
        } catch (error) { message(error.message, true); }
        finally { busy = false; controls(); }
    }
    function placeholders(command) {
        const box = $('command-placeholders'); box.replaceChildren();
        let group;
        for (const item of catalog) {
            if (['result', 'latitude', 'longitude', 'altitude', 'added_scope'].includes(item.name) && command.action === 'reply') continue;
            if (['latitude', 'longitude', 'altitude'].includes(item.name) && command.action !== 'position') continue;
            if (item.name === 'added_scope' && command.action !== 'scope') continue;
            if (item.group !== group) { group = item.group; box.append(node('h4', group)); }
            const token = '{' + item.name + '}';
            const chip = button(token, () => {
                const field = $(activeTemplate), start = field.selectionStart, end = field.selectionEnd;
                field.setRangeText(token, start, end, 'end'); field.focus(); schedulePreview();
            });
            chip.title = item.description; box.append(chip);
        }
    }
    function edit(id = null) {
        if (busy || !snapshot) return;
        currentId = id || ('cmd-' + Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join(''));
        const command = draft.find(c => c.id === currentId) || {trigger: '', help: '', reply: '', action: 'reply', failure_reply: '@{sender_name} | {result}'};
        $('command-editor-title').textContent = id ? 'Edit command' : 'Add command';
        $('command-trigger').value = command.trigger; $('command-trigger').readOnly = currentId === 'help';
        $('command-help').value = command.help; $('command-reply').value = command.reply;
        $('command-action').value = command.action; $('command-action').disabled = currentId === 'help';
        $('command-failure').value = command.failure_reply || '@{sender_name} | {result}';
        activeTemplate = 'command-reply'; actionFields();
        $('command-editor-message').textContent = ''; $('command-preview').textContent = 'Enter a command, help text and reply template.';
        $('command-help-rule').hidden = currentId !== 'help';
        placeholders(command); editor.showModal();
        if (id) preview(true);
        $('command-trigger').focus();
    }
    function actionFields() {
        const action = $('command-action').value;
        $('command-failure-section').hidden = action === 'reply'; $('command-failure-preview-section').hidden = action === 'reply';
        $('command-failure').required = action !== 'reply';
        $('command-action-hint').textContent = action === 'position' ? 'Use command latitude, longitude to save supplied coordinates, or command alone to request fresh GPS telemetry. Requires one matching sender contact. Invalid coordinates leave the saved position unchanged. Position mentions use @[{sender_name}].' : action === 'scope' ? 'Use: command <name> or command add <name>. Adds a reply scope to MeshcoreStation; an existing scope uses the failure reply.' : 'Sends a reply using available data. No additional action.';
        if (action === 'reply') activeTemplate = 'command-reply';
        placeholders({action});
    }
    function closeEditor() {
        if (busy || (formDirty() && !window.confirm('Discard this command’s unfinished edits?'))) return;
        clearTimeout(previewTimer); ++previewSequence; editor.close(); preview();
    }
    async function apply(event) {
        event.preventDefault(); if (busy || !$('command-editor-form').reportValidity()) return;
        clearTimeout(previewTimer); ++previewSequence;
        busy = true; controls();
        try {
            // The server validates the same whitelist used by the runtime renderer.
            const commands = candidateList();
            await request({operation: 'preview', commands, selected_id: currentId});
            draft = commands; editor.close(); render(); await preview();
        } catch (error) { $('command-editor-message').textContent = error.message; }
        finally { busy = false; controls(); }
    }
    function close() {
        if (busy || (dirty() && !window.confirm('Discard unsaved command changes?'))) return;
        clearTimeout(previewTimer); ++previewSequence; dialog.close();
        // Discard the local draft on close; reopening reads the current registry.
        if (snapshot) draft = copy(snapshot.commands);
    }
    function create() {
        dialog = node('dialog'); dialog.id = 'commands-dialog'; dialog.setAttribute('aria-labelledby', 'commands-title');
        dialog.innerHTML = '<div class="dialog-header"><h2 id="commands-title">Commands</h2><button id="commands-close" type="button" aria-label="Close commands">×</button></div><p class="muted">Add commands and define their help text and replies.</p><div class="commands-toolbar"><button id="commands-reload" type="button">Reload</button><button id="commands-add" type="button">＋ Add command</button></div><p id="commands-message" role="status" aria-live="polite"></p><ul id="commands-list"></ul><section class="commands-preview"><h3>Help reply preview</h3><pre id="commands-help-preview"></pre><p class="muted">Built from each command’s help text. Preview only; nothing is sent to the mesh.</p></section>';
        window.meshcorestationPrepareDialog(dialog);
        const footer = node('div', undefined, 'commands-footer'); footer.innerHTML = '<div><p class="muted">? is always available and cannot be deleted or renamed.</p><span id="commands-dirty" role="status"></span></div><button id="commands-cancel" type="button">Cancel</button><button id="commands-save" type="button">Save changes</button>';
        dialog.append(footer); document.body.append(dialog);
        editor = node('dialog'); editor.id = 'command-editor-dialog'; editor.setAttribute('aria-labelledby', 'command-editor-title');
        editor.innerHTML = '<div class="dialog-header"><h2 id="command-editor-title">Edit command</h2><button id="command-editor-close" type="button" aria-label="Close command editor">×</button></div><form id="command-editor-form"><label for="command-trigger">Command</label><input id="command-trigger" required maxlength="30" autocomplete="off"><label for="command-help">Help text</label><input id="command-help" required maxlength="100"><label for="command-action">Action</label><select id="command-action"><option value="reply">Reply</option><option value="position">Update sender position</option><option value="scope">Add scope</option></select><p id="command-action-hint" class="muted"></p><label for="command-reply">Success reply template</label><textarea id="command-reply" rows="4" required maxlength="512"></textarea><div id="command-failure-section" hidden><label for="command-failure">Failure reply template</label><textarea id="command-failure" rows="3" maxlength="512"></textarea></div><p class="muted">Mix your own text with values from MeshcoreStation.</p><p id="command-help-rule" class="muted" hidden>The ? reply must include {command_list}.</p><section class="commands-preview"><h3>Insert data placeholder</h3><div id="command-placeholders"></div><p class="muted">Click a placeholder to insert it at the cursor. Numeric formatting: {snr:.1f} or {battery_voltage:.2f}. Missing values show “unknown”.</p></section><section class="commands-preview"><h3>Reply preview <small class="muted">Example data</small></h3><pre id="command-preview"></pre><p class="muted">Values are filled in when the command is received. Distances are in km without units; ~ means estimated and &gt;= means a lower bound. Battery percentage is an approximate 1S LiPo estimate.</p></section><section id="command-failure-preview-section" class="commands-preview" hidden><h3>Failure reply preview <small class="muted">Example data</small></h3><pre id="command-failure-preview"></pre></section><p id="command-editor-message" class="commands-error" role="status" aria-live="polite"></p></form>';
        window.meshcorestationPrepareDialog(editor);
        const editorFooter = node('div', undefined, 'commands-footer'); editorFooter.innerHTML = '<button id="command-editor-cancel" type="button">Cancel</button><button id="command-editor-apply" type="submit" form="command-editor-form">Apply</button>';
        editor.append(editorFooter); document.body.append(editor);
        $('commands-close').addEventListener('click', close); $('commands-cancel').addEventListener('click', close);
        dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
        $('commands-add').addEventListener('click', () => edit()); $('commands-reload').addEventListener('click', load); $('commands-save').addEventListener('click', save);
        $('command-editor-close').addEventListener('click', closeEditor); $('command-editor-cancel').addEventListener('click', closeEditor);
        editor.addEventListener('cancel', event => { event.preventDefault(); closeEditor(); });
        $('command-action').addEventListener('change', () => { actionFields(); schedulePreview(); });
        for (const id of ['command-reply', 'command-failure']) $(id).addEventListener('focus', () => activeTemplate = id);
        $('command-editor-form').addEventListener('submit', apply); $('command-editor-form').addEventListener('input', schedulePreview);
    }
    function attach() {
        const open = $('open-commands'); if (!open || open.dataset.commandsBound) return;
        open.dataset.commandsBound = 'true';
        open.addEventListener('click', () => { if (!dialog) create(); if (!dialog.open) { dialog.showModal(); load(); } });
    }
    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true}); attach();
})();
