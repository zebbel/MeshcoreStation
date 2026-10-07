(() => {
    let snapshot = null, busy = false;
    const id = name => document.getElementById(name);
    function controls() {
        id('bot-serial-port').disabled = busy || !snapshot;
        id('bot-restart').disabled = busy || !snapshot || !id('bot-serial-port').value || id('bot-serial-port').selectedOptions[0]?.disabled;
        id('bot-ports-refresh').disabled = busy;
    }
    async function request(payload) {
        const options = {cache: 'no-store', headers: {'X-Meshcore-Control': '1'}};
        if (payload) {
            options.method = 'POST'; options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(payload);
        }
        const response = await fetch('/api/bot/runtime', options);
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'Serial settings request failed.');
        return result;
    }
    async function load() {
        if (busy) return;
        busy = true; snapshot = null; controls();
        id('bot-runtime-message').textContent = 'Reading serial ports…';
        try {
            const result = await request(); snapshot = result.settings;
            const select = id('bot-serial-port'); select.replaceChildren();
            for (const port of result.ports) {
                const option = document.createElement('option'); option.value = port.device;
                option.textContent = `${port.device} — ${port.description}`; select.append(option);
            }
            if (!result.ports.some(p => p.device === snapshot.serial_port)) {
                const option = document.createElement('option'); option.value = snapshot.serial_port;
                option.textContent = `${snapshot.serial_port} (saved, unavailable)`; option.disabled = true; select.prepend(option);
            }
            select.value = snapshot.serial_port;
            id('bot-runtime-message').textContent = result.ports.length ? 'Select a port, then save and restart the bot.' : 'No serial ports found. Connect the companion and refresh.';
        } catch (error) { snapshot = null; id('bot-runtime-message').textContent = error.message; }
        finally { busy = false; controls(); }
    }
    async function restart() {
        if (busy || !snapshot) return;
        const payload = {serial_port: id('bot-serial-port').value, expected_serial_port: snapshot.serial_port};
        busy = true; controls(); id('bot-runtime-message').textContent = 'Saving and requesting restart…';
        try {
            const result = await request(payload);
            snapshot.serial_port = payload.serial_port;
            id('bot-runtime-message').textContent = result.message;
        } catch (error) { snapshot = null; id('bot-runtime-message').textContent = `${error.message} Refresh before retrying.`; }
        finally { busy = false; controls(); }
    }
    function attach() {
        const detail = id('serial-panel');
        if (!detail || id('bot-runtime')) return;
        const panel = document.createElement('div'); panel.id = 'bot-runtime';
        panel.innerHTML = `<label for="bot-serial-port">Serial port</label><div class="bot-runtime-controls"><select id="bot-serial-port" aria-label="Serial port"></select><button type="button" id="bot-restart">Save & restart bot</button><button type="button" id="bot-ports-refresh" aria-label="Refresh serial ports">↻</button></div><p id="bot-runtime-message" class="muted" role="status" aria-live="polite"></p>`;
        detail.append(panel);
        id('bot-serial-port').addEventListener('change', controls);
        id('bot-restart').addEventListener('click', restart);
        id('bot-ports-refresh').addEventListener('click', load);
        load();
    }
    new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
    attach();
})();
