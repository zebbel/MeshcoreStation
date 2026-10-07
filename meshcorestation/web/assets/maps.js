(() => {
    const maps = new Map(), requests = new Map();
    function text(tag, value, className) { const el = document.createElement(tag); el.textContent = value; if (className) el.className = className; return el; }
    function dispose(id) { if (maps.has(id)) { maps.get(id).remove(); maps.delete(id); } }
    function describe(node) {
        const box = document.createElement('div');
        box.append(text('strong', node.label), text('p', node.role === 'repeater' && node.order ? `Repeater hop ${node.order}` : node.role));
        box.append(text('p', node.position.map(n => n.toFixed(6)).join(', ')));
        if (node.public_key) box.append(text('p', node.public_key, 'map-key'));
        if (node.updated_at) box.append(text('p', `Saved / last seen: ${new Date(node.updated_at * 1000).toLocaleString()}`));
        if (node.role === 'repeater' && node.public_key) {
            const battery = text('button', 'Battery history'); battery.type = 'button';
            battery.addEventListener('click', () => {
                document.getElementById('repeaters-dialog')?.close();
                document.getElementById('details-dialog')?.close();
                document.dispatchEvent(new CustomEvent('meshcore-voltage-open', {detail: {public_key: node.public_key}}));
            });
            box.append(battery);
        }
        return box;
    }
    async function load(id, url, notesId, hopsId) {
        requests.get(id)?.abort();
        const controller = new AbortController(); requests.set(id, controller);
        const canvas = document.getElementById(id), notes = document.getElementById(notesId), hops = hopsId && document.getElementById(hopsId);
        dispose(id); canvas.replaceChildren(); notes.replaceChildren(text('p', 'Loading map…')); if (hops) hops.replaceChildren();
        try {
            const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Map data could not be loaded.');
            if (controller.signal.aborted) return;
            notes.replaceChildren(...data.notes.map(note => text('p', note)));
            if (hops) for (const hop of data.hops) hops.append(text('li', `${hop.number}. ${hop.name} · ${hop.hash} · ${hop.status}`));
            if (!window.L) throw new Error('Map library could not be loaded. Refresh the page and try again.');
            const map = L.map(canvas, { scrollWheelZoom: true }).setView([51, 10], 5); maps.set(id, map);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' }).on('tileerror', () => {
                if (!notes.querySelector('.tile-warning')) notes.append(text('p', 'Background tiles unavailable. Markers and route lines remain visible; an Internet connection is needed for the basemap.', 'tile-warning'));
            }).addTo(map);
            for (const line of data.segments) L.polyline(line, { color: '#4d8eff', weight: 4, opacity: 0.85 }).addTo(map);
            for (const node of data.nodes) {
                const marker = text('span', node.role === 'sender' ? 'S' : node.role === 'bot' ? 'B' : node.order || 'R', 'map-marker ' + node.role);
                const icon = L.divIcon({ html: marker, className: 'map-icon', iconSize: [28, 28], iconAnchor: [14, 14] });
                L.marker(node.position, { icon, title: `${node.role}: ${node.label}`, zIndexOffset: node.role === 'repeater' ? 0 : 100 }).addTo(map).bindPopup(describe(node));
            }
            notes.prepend(text('p', 'S = sender · numbered markers / R = repeaters · B = bot. Click markers for details.', 'map-legend'));
            if (!data.nodes.length) notes.prepend(text('p', 'No usable coordinates are available for this map.'));
            requestAnimationFrame(() => { if (maps.get(id) !== map) return; map.invalidateSize(); if (data.nodes.length) map.fitBounds(data.nodes.map(node => node.position), { padding: [35, 35], maxZoom: 14 }); });
        } catch (error) { if (error.name !== 'AbortError') notes.replaceChildren(text('p', error.message)); }
    }
    function cleanup(id) { requests.get(id)?.abort(); dispose(id); }
    document.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (button?.dataset.details) {
            const record = JSON.parse(button.dataset.details), section = document.getElementById('route-section');
            section.hidden = String(record.message || '').trim().toLowerCase() !== 'ping';
            if (!section.hidden) load('route-map', `/api/maps/route/${encodeURIComponent(record.id)}`, 'route-notes', 'route-hops');
            else cleanup('route-map');
        }
        const dialog = document.getElementById('repeaters-dialog');
        if (button?.id === 'open-repeaters') { dialog.showModal(); load('repeater-map', '/api/maps/repeaters', 'repeater-notes'); document.getElementById('close-repeaters').focus(); }
        if (button?.id === 'close-repeaters') dialog.close();
        if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); }
    });
    document.addEventListener('close', event => {
        if (event.target.id === 'repeaters-dialog') cleanup('repeater-map');
        if (event.target.id === 'details-dialog') cleanup('route-map');
    }, true);
})();
