/* Map selection changes draft coordinates only; Save section performs the radio write. */
window.MeshcoreStationRepeaterLocation = (() => {
    let dialog, map, currentMarker, selectedMarker, picked, context;
    const $ = id => document.getElementById(id);
    function position(pair) {
        if (!pair || pair.some(value => value == null || String(value).trim() === '')) return null;
        const [lat, lon] = pair.map(Number);
        return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && (lat !== 0 || lon !== 0) ? [lat, lon] : null;
    }
    function sync(center = false) {
        const current = position(context.current);
        if (current) {
            if (!currentMarker) currentMarker = L.circleMarker(current, {radius: 22, color: '#087b55', weight: 4, fillColor: '#087b55', fillOpacity: 0.15}).addTo(map).bindTooltip('Current repeater position');
            else currentMarker.setLatLng(current);
        } else if (currentMarker) { currentMarker.remove(); currentMarker = null; }
        if (picked) {
            if (!selectedMarker) {
                const icon = L.divIcon({html: '<span class="map-marker bot">R</span>', className: 'map-icon', iconSize: [28, 28], iconAnchor: [14, 14]});
                selectedMarker = L.marker(picked, {icon, draggable: true, title: 'Selected position — drag to move'}).addTo(map);
                selectedMarker.on('dragend', event => select(event.target.getLatLng()));
            } else selectedMarker.setLatLng(picked);
        } else if (selectedMarker) { selectedMarker.remove(); selectedMarker = null; }
        $('repeater-map-current').textContent = current ? 'Current: ' + current.map(n => n.toFixed(6)).join(', ') : 'The repeater has no valid current position.';
        $('repeater-map-selection').textContent = picked ? 'Selected: ' + picked.map(n => n.toFixed(6)).join(', ') : 'Click the map to select a position.';
        $('repeater-map-apply').disabled = !picked || !context.canEdit();
        map.invalidateSize();
        if (center) {
            const points = [current, picked].filter(Boolean);
            if (points.length) map.fitBounds(points, {padding: [40, 40], maxZoom: 16}); else map.setView([51, 10], 5);
        }
    }
    function select(point) {
        if (!context.canEdit()) return;
        const wrapped = point.wrap(); picked = position([Number(wrapped.lat.toFixed(6)), Number(wrapped.lng.toFixed(6))]); sync();
    }
    function create() {
        dialog = document.createElement('dialog'); dialog.id = 'repeater-location-dialog'; dialog.setAttribute('aria-labelledby', 'repeater-map-title');
        dialog.innerHTML = '<div class="dialog-header"><h2 id="repeater-map-title">Choose repeater position</h2><button type="button" id="repeater-map-close" aria-label="Close repeater position map">×</button></div><p class="muted">Green ring = current repeater position. Orange R = selected position. Click or drag to select; scroll to zoom.</p><p id="repeater-map-current" class="muted"></p><div id="repeater-location-map" class="map-canvas" role="region" aria-label="Repeater position picker"></div><p id="repeater-map-selection" role="status" aria-live="polite"></p><p id="repeater-map-error" class="muted"></p><div class="position-map-actions"><button type="button" id="repeater-map-cancel">Cancel</button><button type="button" id="repeater-map-apply" class="info-button">Apply</button></div>';
        window.meshcorestationPrepareDialog(dialog); document.body.append(dialog);
        $('repeater-map-close').addEventListener('click', () => dialog.close());
        $('repeater-map-cancel').addEventListener('click', () => dialog.close());
        $('repeater-map-apply').addEventListener('click', () => { if (picked && context.canEdit()) { context.apply(picked); dialog.close(); } });
        map = L.map('repeater-location-map', {scrollWheelZoom: true, worldCopyJump: true}).setView([51, 10], 5);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, noWrap: true, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'}).on('tileerror', () => { $('repeater-map-error').textContent = 'Background tiles unavailable. Check your Internet connection or use the coordinate fields.'; }).addTo(map);
        map.on('click', event => select(event.latlng));
        new ResizeObserver(() => { if (dialog.open) map.invalidateSize(); }).observe($('repeater-location-map'));
    }
    return {open(options) {
        if (!options.canEdit()) return;
        if (!window.L) { options.report('Map library unavailable. Refresh the page or enter coordinates manually.', true); return; }
        context = options;
        if (!dialog) create();
        picked = position(context.draft) || position(context.current); dialog.showModal(); sync(true);
    }};
})();
