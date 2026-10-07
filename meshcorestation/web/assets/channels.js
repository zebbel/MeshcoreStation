(() => {
    let dialog, snapshot = null, busy = false;
    const byId = id => document.getElementById(id);
    const types = {public: ['🌐', 'Public'], hashtag: ['#️⃣', 'Hashtag'], private: ['🔒', 'Private']};

    function message(text, error = false) {
        byId('channels-message').textContent = text;
        byId('channels-message').classList.toggle('channels-error', error);
    }

    function controls() {
        dialog.querySelectorAll('button, input, select').forEach(element => {
            element.disabled = busy || element.dataset.protected === 'true' || (!snapshot && element.closest('#channel-form, #channels-list'));
        });
        byId('channels-add').disabled = busy || !snapshot || snapshot.free_slots === 0;
        dialog.setAttribute('aria-busy', String(busy));
    }

    function dirty() {
        return ['channel-name', 'channel-key'].some(id => byId(id).value !== '') || byId('channel-type').value !== 'hashtag';
    }

    function close() {
        if (!busy && (!dirty() || window.confirm('Discard the unfinished channel?'))) dialog.close();
    }

    async function request(payload) {
        const options = {cache: 'no-store', headers: {'X-Meshcore-Control': '1'}};
        if (payload) {
            options.method = 'POST'; options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(payload);
        }
        const response = await fetch('/api/companion/channels', options);
        let result;
        try { result = await response.json(); }
        catch { throw new Error('Unreadable response. Refresh before retrying; a submitted change may have applied.'); }
        if (!response.ok || !result.ok) throw new Error(result.error || 'Request failed. Refresh channels.');
        if (!Array.isArray(result.channels) || typeof result.public_key !== 'string') throw new Error('Incomplete channel response.');
        return result;
    }

    function render(result) {
        snapshot = result;
        byId('channels-identity').textContent = `Connected companion: ${result.public_key}`;
        byId('channels-count').textContent = `${result.channels.length} / ${result.capacity} channels · ${result.free_slots} slots available`;
        const list = byId('channels-list'); list.replaceChildren();
        for (const channel of result.channels) {
            const row = document.createElement('li'), icon = document.createElement('span');
            const text = document.createElement('div'), name = document.createElement('strong');
            const details = document.createElement('small'), button = document.createElement('button');
            const [symbol, label] = types[channel.type] || ['◆', `Type ${channel.type}`];
            icon.className = 'channel-icon'; icon.textContent = symbol; icon.setAttribute('aria-hidden', 'true');
            name.textContent = channel.name || '(unnamed)';
            details.textContent = `${label} · Slot ${channel.index}${channel.protected ? ' · Used by bot' : ''}`;
            button.dataset.protected = String(channel.protected);
            if (channel.protected) button.title = 'The running bot needs this channel.';
            text.className = 'channel-label'; text.append(name, details);
            button.type = 'button'; button.textContent = 'Delete'; button.className = 'channel-delete';
            button.setAttribute('aria-label', `Delete ${channel.name || `slot ${channel.index}`}`);
            button.addEventListener('click', () => remove(channel));
            const select = document.createElement('button');
            select.type = 'button'; select.textContent = channel.protected ? 'Bot channel ✓' : 'Bot channel';
            select.dataset.protected = String(channel.protected);
            select.setAttribute('aria-label', `Use ${channel.name || 'unnamed'} as bot channel`);
            select.addEventListener('click', async () => {
                if (busy || !snapshot || channel.protected) return;
                await mutate({operation: 'set_bot_channel', index: channel.index,
                    expected_public_key: snapshot.public_key, expected_revision: snapshot.revision},
                    'Bot channel saved and activated.');
            });
            row.append(icon, text, select, button); list.append(row);
        }
        if (!result.channels.length) {
            const empty = document.createElement('li'); empty.textContent = 'The companion has no saved channels.'; list.append(empty);
        }
    }

    async function load() {
        if (busy) return;
        busy = true; snapshot = null; controls(); message('Reading channels from the companion…');
        try { render(await request()); message('Channels loaded from the companion.'); }
        catch (error) { message(error.message, true); }
        finally { busy = false; controls(); }
    }

    async function mutate(payload, success) {
        busy = true; controls(); message('Saving and verifying the channel list…');
        try {
            const result = await request(payload);
            if (result.public_key !== payload.expected_public_key) throw new Error('Companion changed. Refresh channels.');
            render(result); message(success);
            return true;
        } catch (error) {
            snapshot = null;
            message(`${error.message} Use Refresh before another change.`, true);
            return false;
        } finally { busy = false; controls(); }
    }

    async function remove(channel) {
        if (busy || !snapshot || channel.protected) return;
        if (!window.confirm(`Delete ${channel.name || '(unnamed)'} from slot ${channel.index}?\n\nRemove this channel from the companion?`)) return;
        await mutate({operation: 'delete_channel', index: channel.index,
            expected_revision: snapshot.revision, expected_public_key: snapshot.public_key,
            confirm_delete: true}, 'Channel deletion verified.');
    }

    function typeFields() {
        const kind = byId('channel-type').value;
        byId('channel-name-label').hidden = false;
        byId('channel-name').required = true;
        byId('channel-key-field').hidden = kind !== 'private';
        byId('channel-key').required = kind === 'private';
        byId('channel-name').placeholder = kind === 'hashtag' ? '#local' : 'Channel name';
    }

    async function add(event) {
        event.preventDefault();
        if (busy || !snapshot || !byId('channel-form').reportValidity()) return;
        const kind = byId('channel-type').value;
        let name = byId('channel-name').value.trim();
        if (kind === 'hashtag' && !name.startsWith('#')) name = '#' + name;
        if (!name || name === '#' || new TextEncoder().encode(name).length > 31 || /[\x00-\x1f\x7f]/.test(name)) {
            message('Use a name of 1–31 UTF-8 bytes, including #, without control characters.', true); return;
        }
        const value = {name, type: kind};
        if (kind === 'private') value.secret = byId('channel-key').value.trim();
        if (await mutate({operation: 'add_channel', expected_public_key: snapshot.public_key,
            expected_revision: snapshot.revision, value}, 'Channel addition verified.')) {
            byId('channel-form').reset(); typeFields(); byId('channel-form').hidden = true;
            byId('channels-add').setAttribute('aria-expanded', 'false'); byId('channels-refresh').focus();
        }
    }

    function create() {
        dialog = document.createElement('dialog'); dialog.id = 'channels-dialog'; dialog.setAttribute('aria-labelledby', 'channels-title');
        dialog.innerHTML = `<div class="dialog-header"><h2 id="channels-title">Companion channels</h2><button type="button" id="channels-close" aria-label="Close channels">×</button></div>
            <p id="channels-identity" class="muted"></p><div class="channels-toolbar"><button type="button" id="channels-refresh">Refresh</button><button type="button" id="channels-add" class="info-button" aria-expanded="false" aria-controls="channel-form">Add channel</button><span id="channels-count" class="muted"></span></div>
            <p id="channels-message" role="status" aria-live="polite"></p>
            <form id="channel-form" hidden><h3>Add channel</h3><div class="channel-fields">
            <label>Type<select id="channel-type"><option value="hashtag">#️⃣ Hashtag</option><option value="private">🔒 Private</option><option value="public">🌐 Public</option></select></label>
                <label id="channel-name-label">Name<input id="channel-name" maxlength="31" required autocomplete="off"></label>
                <div id="channel-key-field" class="channel-key-field" hidden><label>Private key (32 hex characters or base64)<input id="channel-key" maxlength="32" spellcheck="false" autocomplete="off"></label><button type="button" id="channel-generate">Generate key</button><p class="muted">Paste an existing channel key to join it, or generate a key to create a new private channel. Copy a generated key before saving so you can share it with your other devices.</p></div></div>
                <p class="muted">Public channels share the public key regardless of their name. Hashtag channels derive their key from the name. A private channel requires its key. The first empty slot is used.</p>
            <div class="channels-toolbar"><button type="submit" class="info-button">Save channel</button><button type="button" id="channel-cancel">Cancel</button></div></form>
            <ul id="channels-list"></ul>`;
        window.meshcorestationPrepareDialog(dialog);
        document.body.append(dialog);
        byId('channels-close').addEventListener('click', close);
        dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
        byId('channels-refresh').addEventListener('click', load);
        byId('channel-form').addEventListener('submit', add);
        byId('channel-type').addEventListener('change', typeFields);
        byId('channel-generate').addEventListener('click', () => {
            if (byId('channel-key').value && !window.confirm('Replace the entered private key?')) return;
            const bytes = crypto.getRandomValues(new Uint8Array(16));
            byId('channel-key').value = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
        });
        typeFields();
        byId('channels-add').addEventListener('click', () => {
            byId('channel-form').hidden = false; byId('channels-add').setAttribute('aria-expanded', 'true'); byId('channel-type').focus();
        });
        byId('channel-cancel').addEventListener('click', () => {
            if (dirty() && !window.confirm('Discard the unfinished channel?')) return;
            byId('channel-form').reset(); typeFields(); byId('channel-form').hidden = true; byId('channels-add').setAttribute('aria-expanded', 'false'); byId('channels-add').focus();
        });
    }

    function attach() {
        const settings = byId('open-contacts');
        if (!settings || byId('open-channels')) return;
        const button = document.createElement('button'); button.id = 'open-channels'; button.type = 'button';
        button.className = 'info-button'; button.textContent = 'Channels';
        settings.insertAdjacentElement('afterend', button);
        settings.parentElement.classList.add('has-channels');
    }

    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
    document.addEventListener('click', event => {
        if (!event.target.closest('#open-channels')) return;
        if (!dialog) create();
        if (dialog.open) return;
        snapshot = null; byId('channel-form').reset(); typeFields(); byId('channel-form').hidden = true;
        byId('channels-add').setAttribute('aria-expanded', 'false');
        byId('channels-list').replaceChildren(); byId('channels-count').textContent = ''; byId('channels-identity').textContent = '';
        dialog.showModal(); load();
    });
    attach();
})();