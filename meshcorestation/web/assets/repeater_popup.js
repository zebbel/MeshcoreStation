(() => {
    let contactsRequest;
    async function request(url, body) {
        const response = await fetch(url, {cache: 'no-store', headers: {'X-Meshcore-Control': '1', 'Content-Type': 'application/json'}, ...(body ? {method: 'POST', body: JSON.stringify(body)} : {})});
        const result = await response.json();
        if (!response.ok || !result.ok) throw Error(result.error || 'Request failed. Reopen the popup to retry.');
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
        button.type = battery.type = 'button'; button.textContent = 'Checking contacts…'; battery.textContent = 'Battery history';
        button.disabled = battery.disabled = true; status.setAttribute('role', 'status');
        box.append(button, battery, status);
        let snapshot;
        const render = data => {
            snapshot = data;
            button.disabled = data.contacts.some(c => c.public_key.toLowerCase() === key);
            button.textContent = button.disabled ? 'Already in contacts' : 'Add to contacts';
        };
        contacts().then(render).catch(error => {button.textContent = 'Contacts unavailable';status.textContent = error.message;});
        request('/api/bot/voltage?days=1').then(data => {
            battery.disabled = data.config.public_key?.toLowerCase() === key;
            if (battery.disabled) battery.title = 'Already selected for battery monitoring';
        }).catch(error => {status.textContent = error.message;});
        battery.onclick = () => {close();document.dispatchEvent(new CustomEvent('meshcore-voltage-open', {detail: {public_key: key}}));};
        button.onclick = async () => {
            if (button.disabled || !snapshot) return;
            button.disabled = true;status.textContent = 'Adding contact…';
            try {
                const value = {public_key: key, name: repeater.name || repeater.label || key.slice(0, 12), type: 2};
                const position = repeater.position || [repeater.latitude, repeater.longitude];
                if (position.every(Number.isFinite)) [value.latitude, value.longitude] = position;
                const data = await request('/api/companion/contacts', {operation: 'add_contact', expected_public_key: snapshot.public_key, value});
                if (data.public_key !== snapshot.public_key) throw Error('Companion changed. Reopen the popup.');
                render(data);status.textContent = 'Contact saved.';
            } catch (error) {status.textContent = error.message + ' Reopen the popup to refresh contacts.';}
        };
    };
})();
