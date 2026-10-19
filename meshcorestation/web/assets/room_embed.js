/* Resize the same-origin Room server page embedded in the Dash dashboard. */
(() => {
    window.addEventListener('message', event => {
        const frame = document.getElementById('room-server-frame');
        if (!frame || event.origin !== window.location.origin || event.source !== frame.contentWindow) return;
        if (!event.data || event.data.kind !== 'meshcorestation-room-iframe-height') return;
        const height = event.data.height;
        if (typeof height !== 'number' || !Number.isFinite(height)) return;
        frame.style.height = Math.max(120, Math.min(10000, Math.ceil(height))) + 'px';
    });
})();
