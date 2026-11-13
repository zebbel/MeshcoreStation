(() => {
    const {translatedError: uiError, t: ui} = window.MeshcoreStationI18n || {
        translatedError: value => value,
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`))
    };
    let contactsRequest;
    async function request(url, body) {
        const response = await fetch(url, {cache: 'no-store', headers: {'X-Meshcore-Control': '1', 'Content-Type': 'application/json'}, ...(body ? {method: 'POST', body: JSON.stringify(body)} : {})});
        const result = await response.json();
        if (!response.ok || !result.ok) throw Error(result.error || ui("Request failed. Reopen the popup to retry."));
        return result;
    }
    function contacts() {
        if (!contactsRequest) {
            contactsRequest = request('/api/companion/contacts');
            contactsRequest.finally(() => { contactsRequest = null; }).catch(() => {});
        }
        return contactsRequest;
    }
    window.meshcorestationRepeaterActions = (box, repeater, close) => {
        const key = repeater.public_key.toLowerCase();
        const button = document.createElement('button'), battery = document.createElement('button'), status = document.createElement('p');
        button.type = battery.type = 'button'; button.textContent = ui("Checking contacts…"); battery.textContent = ui("Telemetry history");
        button.disabled = battery.disabled = true; status.setAttribute('role', 'status');
        box.append(button, battery, status);
        let snapshot;
        const render = data => {
            snapshot = data;
            button.disabled = data.contacts.some(c => c.public_key.toLowerCase() === key);
            button.textContent = button.disabled ? ui("Already in contacts") : ui("Add to contacts");
        };
        contacts().then(render).catch(error => {button.textContent = ui("Contacts unavailable");status.textContent = uiError(error.message);});
        request('/api/bot/voltage?days=1').then(data => {
            battery.disabled = data.config.public_key?.toLowerCase() === key;
            if (battery.disabled) battery.title = ui("Already selected for telemetry monitoring");
        }).catch(error => {status.textContent = uiError(error.message);});
        battery.onclick = () => {close();document.dispatchEvent(new CustomEvent('meshcore-voltage-open', {detail: {public_key: key}}));};
        button.onclick = async () => {
            if (button.disabled || !snapshot) return;
            button.disabled = true;status.textContent = ui("Adding contact…");
            try {
                const value = {public_key: key, name: repeater.name || repeater.label || key.slice(0, 12), type: 2};
                const position = repeater.position || [repeater.latitude, repeater.longitude];
                if (position.every(Number.isFinite)) [value.latitude, value.longitude] = position;
                const data = await request('/api/companion/contacts', {operation: 'add_contact', expected_public_key: snapshot.public_key, value});
                if (data.public_key !== snapshot.public_key) throw Error(ui("Companion changed. Reopen the popup."));
                render(data);status.textContent = ui("Contact saved.");
            } catch (error) {status.textContent = error.message + ui(" Reopen the popup to refresh contacts.");}
        };
    };
})();
