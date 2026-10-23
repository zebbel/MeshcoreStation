(() => {
    const maps = new Map(), requests = new Map(), cache = new Map(), observers = new Map();
    const cacheTTL = 30000;
    async function mapData(url, signal) {
        const saved=cache.get(url);
        if(saved && Date.now()-saved.at<cacheTTL){cache.delete(url);cache.set(url,saved);return saved.data;}
        const response=await fetch(url,{cache:"no-store",signal});
        let data;
        try { data=await response.json(); }
        catch { throw Error('Map API returned an invalid response. Reload the page and try again.'); }
        if(!response.ok)throw Error(data?.error||`Map data request failed (HTTP ${response.status}). Try again.`);
        if (!data || !['nodes','segments','notes','hops'].every(key => Array.isArray(data[key])))
            throw Error('Map API returned incomplete map data. Reload the page and try again.');
        cache.set(url,{at:Date.now(),data});
        while(cache.size>32)cache.delete(cache.keys().next().value);
        return data;
    }
    function text(tag, value, className) { const el = document.createElement(tag); el.textContent = value; if (className) el.className = className; return el; }
    function dispose(id) {
        observers.get(id)?.disconnect(); observers.delete(id);
        if (maps.has(id)) {
            try { maps.get(id).remove(); }
            catch (error) { console.warn('Map cleanup failed:', error); }
            finally { maps.delete(id); }
        }
    }
    function frame(signal) {
        return new Promise((resolve, reject) => {
            if (signal.aborted) { resolve(false); return; }
            let handle;
            const abort = () => { window.cancelAnimationFrame?.(handle); resolve(false); };
            signal.addEventListener('abort', abort, {once:true});
            try { handle = requestAnimationFrame(() => { signal.removeEventListener('abort', abort); resolve(!signal.aborted); }); }
            catch (error) { signal.removeEventListener('abort', abort); reject(error); }
        });
    }
    function describe(node) {
        const box = document.createElement('div');
        box.append(text('strong', node.label), text('p', node.role === 'repeater' && node.order ? `Repeater hop ${node.order}` : node.role));
        box.append(text('p', node.position.map(n => n.toFixed(6)).join(', ')));
        if (node.public_key) box.append(text('p', node.public_key, 'map-key'));
        if (node.updated_at) box.append(text('p', `Saved / last seen: ${window.meshcorestationFormatDate(node.updated_at)}`));
        if (node.role === 'repeater' && node.public_key) {
            window.meshcorestationRepeaterActions(box, node, () => {
                document.getElementById('repeaters-dialog')?.close();
                document.getElementById('details-dialog')?.close();
            });
        }
        return box;
    }
    async function load(id, url, notesId) {
        requests.get(id)?.abort();
        const controller = new AbortController(); requests.set(id, controller);
        const canvas = document.getElementById(id), notes = document.getElementById(notesId);
        const summary = id === 'route-map' && document.getElementById('route-summary');
        if (summary) summary.replaceChildren(text('p', 'Loading distances and packet route…'));
        if (summary) document.getElementById('route-paths')?.replaceChildren();
        dispose(id); canvas.replaceChildren();
        const loading = text('p', 'Loading map…', 'map-loading');
        loading.setAttribute('role','status');
        notes.replaceChildren(loading); canvas.setAttribute('aria-busy','true');
        let timedOut = false, failed = false;
        function fail(error) {
            if (failed || requests.get(id) !== controller || (controller.signal.aborted && !timedOut)) return;
            failed = true; controller.abort();
            dispose(id); canvas.replaceChildren(); canvas.setAttribute('aria-busy','false');
            const message = timedOut ? 'Map loading timed out. Check the connection and try again.' : String(error?.message || error || 'Map initialization failed. Try again.');
            const failure = text('p', message, 'map-error'); failure.setAttribute('role','alert');
            const retry = text('button','Retry map'); retry.type='button'; retry.addEventListener('click',()=>load(id,url,notesId));
            notes.replaceChildren(failure,retry);
            if (summary && summary.textContent === 'Loading distances and packet route…') summary.replaceChildren(text('p', 'Distances and packet route could not be loaded.'));
        }
        const timeout = setTimeout(() => { timedOut = true; fail(); }, 30000);
        try {
            // Route details must not wait for map scripts or background tiles.
            const library = window.meshcorestationLoadMapLibrary({clustering:id==='repeater-map'});
            // Attach a rejection handler immediately while route data is fetched.
            const ready=library.then(()=>null,error=>error);
            const payload = await mapData(url, controller.signal);
            const alternatives = payload.reception_paths || [payload];
            let data = alternatives[0], redraw = null;
            const selector = summary && document.getElementById('route-paths');
            if (selector) selector.replaceChildren();
            function showRoute() {
                if (controller.signal.aborted) return;
                const tileWarning = notes.querySelector('.tile-warning');
                notes.replaceChildren(...data.notes.map(note => text('p', note)));
                if (tileWarning) notes.append(tileWarning);
                if (canvas.getAttribute('aria-busy') === 'true') notes.prepend(loading);
                if (summary) notes.prepend(text('p', 'S = sender · numbered markers = repeaters · B = bot. Blue = resolved route; red dashed = unresolved section. Arrows point toward the bot.', 'map-legend'));
                if (summary) {
                    const distance = value => typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)} km` : 'Not available';
                    const sequence = [data.sender_name || 'Sender', ...data.hops.map(hop => hop.status === 'Resolved' || hop.status === 'Coordinates missing' ? hop.name : `${hop.hash} (${hop.status})`), data.bot_name || 'Bot'];
                    if (!data.path_valid) sequence.splice(1, 0, 'Route not recorded / invalid');
                    summary.replaceChildren(
                        text('p', `Direct distance: ${distance(data.direct_distance_km)} · Route distance: ${data.route_distance_lower_bound ? '≥ ' : ''}${distance(data.route_distance_km)}`, 'route-distances'),
                        text('p', sequence.join(' → '), 'route-sequence'));
                    if (data.path_valid && !data.hops.length) summary.append(text('p', 'Direct packet · no repeaters', 'muted'));
                }
            }
            showRoute();
            if (selector) alternatives.forEach((route, index) => {
                const rx = route.reception || {}, button = text('button', '');
                button.type = 'button';
                const metric = (value, unit) => typeof value === 'number' ? `${value} ${unit}` : 'Unknown';
                const hops = route.path_valid ? `${route.hops.length} hops` : 'Unknown / incomplete path';
                const unresolved = route.hops.some(hop => hop.status !== 'Resolved') ? ' · Unresolved: ' + route.hops.filter(hop => hop.status !== 'Resolved').map(hop => hop.status).join(', ') : '';
                button.textContent = `Path ${index+1} · ${hops}${unresolved} · RSSI ${metric(rx.rssi,'dBm')} · SNR ${metric(rx.snr,'dB')} · ${rx.recv_time == null ? 'Time unknown' : window.meshcorestationFormatDate(rx.recv_time)}${rx.observations?.length > 1 ? ` · ${rx.observations.length} receptions` : ''}`;
                button.setAttribute('aria-pressed', String(index === 0));
                button.addEventListener('click', () => {
                    if (controller.signal.aborted) return;
                    data = route;
                    for (const item of selector.children) item.setAttribute('aria-pressed', String(item === button));
                    showRoute();
                    if (redraw) redraw();
                });
                selector.append(button);
            });
            const libraryError=await ready;
            if(controller.signal.aborted)return;
            if(libraryError)throw libraryError;
            if (!window.L) throw new Error('Map library could not be loaded. Refresh the page and try again.');
            // MarkerCluster needs a finite zoom limit before background tiles exist.
            if (!await frame(controller.signal)) return;
            const map = L.map(canvas, { scrollWheelZoom: true, maxZoom: 19 }); maps.set(id, map);
            // Set final bounds before attaching OSM tiles: no wasted requests at the default location.
            const bounds = alternatives.flatMap(route => route.nodes.map(node => node.position));
            if (bounds.length) map.fitBounds(bounds, { padding: [35, 35], maxZoom: 14 });
            else map.setView([51, 10], 5);
            const clusters = id === 'repeater-map' ? window.meshcorestationMarkerClusters(map) : null;
            let overlays = [], endpointsDrawn = false;
            const add = layer => { overlays.push(layer); return layer.addTo(map); };
            function draw() {
                for (const layer of overlays) map.removeLayer(layer);
                overlays = [];
                for (const segment of data.segments) {
                    const line = segment.positions, color = segment.unresolved ? '#ef5350' : '#4d8eff';
                    add(L.polyline(line, { color, weight: 4, opacity: 0.9, dashArray: segment.unresolved ? '9 8' : null }));
                    // Mercator midpoint and screen angle keep the arrow on the rendered line at every zoom.
                    const start = map.project(line[0], 0), end = map.project(line[1], 0);
                    if (Math.hypot(end.x - start.x, end.y - start.y) > 1e-9) {
                        const midpoint = map.unproject([(start.x + end.x) / 2, (start.y + end.y) / 2], 0);
                        const arrow = text('span', '', 'route-direction-arrow');
                        arrow.style.borderLeftColor = color;
                        arrow.style.transform = `rotate(${Math.atan2(end.y - start.y, end.x - start.x)}rad)`;
                        arrow.setAttribute('aria-hidden', 'true');
                        const icon = L.divIcon({html: arrow, className: 'route-arrow-icon', iconSize: [20, 20], iconAnchor: [10, 10]});
                        add(L.marker(midpoint, {icon, interactive: false, keyboard: false, zIndexOffset: -100}));
                    }
                }

                if (!clusters) for (const node of data.nodes) {
                    const endpoint = summary && node.role !== 'repeater';
                    if (endpoint && endpointsDrawn) continue;
                    const layer = markerFor(node);
                    if (endpoint) layer.addTo(map);
                    else add(layer);
                }
                endpointsDrawn = true;
            }
            function markerFor(node) {
                const marker = text('span', node.role === 'sender' ? 'S' : node.role === 'bot' ? 'B' : node.order || 'R', 'map-marker ' + node.role);
                const icon = L.divIcon({ html: marker, className: 'map-icon', iconSize: [28, 28], iconAnchor: [14, 14] });
                return L.marker(node.position, { icon, title: `${node.role}: ${node.label}`, zIndexOffset: node.role === 'repeater' ? 0 : 100 }).bindPopup(() => describe(node));
            }
            redraw = draw;
            draw();
            if (clusters) {
                // Bulk cluster insertion avoids an icon/layout update per marker.
                // Small batches yield to touch input, close events and painting.
                for (let offset=0; offset<data.nodes.length; offset+=100) {
                    if (controller.signal.aborted) return;
                    const batch = [];
                    for (const node of data.nodes.slice(offset,offset+100)) {
                        const marker = markerFor(node);
                        if (node.role === 'repeater') batch.push(marker);
                        else add(marker);
                    }
                    clusters.addLayers(batch);
                    loading.textContent = `Loading map… ${Math.min(offset+100,data.nodes.length)} / ${data.nodes.length} markers`;
                    await new Promise(resolve => setTimeout(resolve,0));
                }
            }
            if (clusters) notes.prepend(text('p', 'Numbered circles group nearby repeaters. Zoom in or click a group to expand it; overlapping markers spread apart when expanded.', 'map-legend'));
            if (!summary) notes.prepend(text('p', 'S = sender · numbered markers / R = repeaters · B = bot. Click markers for details.', 'map-legend'));
            if (!data.nodes.length) notes.prepend(text('p', 'No usable coordinates are available for this map.'));
            if (!await frame(controller.signal) || maps.get(id) !== map) return;
            map.invalidateSize();
            if (bounds.length) map.fitBounds(bounds, {padding:[35,35],maxZoom:14});
            // Draw overlays before tiles; await these steps so failures are visible.
            if (!await frame(controller.signal) || maps.get(id) !== map) return;
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' }).on('tileerror', () => {
                if (!notes.querySelector('.tile-warning')) notes.append(text('p', 'Background tiles unavailable. Markers and route lines remain visible; an Internet connection is needed for the basemap.', 'tile-warning'));
            }).addTo(map);
            if (window.ResizeObserver) {
                const observer = new ResizeObserver(() => {
                    if (maps.get(id) === map && canvas.clientWidth && canvas.clientHeight) {
                        try { map.invalidateSize({pan:false}); } catch (error) { fail(error); }
                    }
                });
                observers.set(id,observer); observer.observe(canvas);
            }
            loading.remove();
            notes.prepend(text('p', `Map ready · ${data.nodes.length} markers.`, 'map-ready'));
        } catch (error) {
            fail(error);
        } finally {
            clearTimeout(timeout);
            if (requests.get(id) === controller) canvas.setAttribute('aria-busy','false');
        }
    }

    function cleanup(id) { requests.get(id)?.abort(); dispose(id); }
    document.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (button?.dataset.details) {
            const record = JSON.parse(button.dataset.details), section = document.getElementById('route-section');
            section.hidden = false;
            load('route-map', `/api/maps/route/${encodeURIComponent(record.id)}`, 'route-notes');
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
