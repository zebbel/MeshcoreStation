/* Lazy room administration, same-origin sizing, and visibility handoff. */
(() => {
    function visible() {
        const section = document.getElementById('room-server-disclosure');
        const frame = document.getElementById('room-server-frame');
        if (!section || !frame) return;
        if (section.open && !frame.getAttribute('src')) frame.src = frame.dataset.src;
        frame.contentWindow?.postMessage({kind:'meshcorestation-room-visible',visible:section.open && !document.hidden},location.origin);
    }
    document.addEventListener('toggle', event => { if(event.target.id==='room-server-disclosure')visible(); },true);
    document.addEventListener('visibilitychange',visible);
    window.addEventListener('message', event => {
        const frame = document.getElementById('room-server-frame');
        if (!frame || event.origin !== location.origin || event.source !== frame.contentWindow) return;
        if(event.data?.kind==='meshcorestation-room-ready'){visible();return;}
        if(event.data?.kind!=='meshcorestation-room-iframe-height')return;
        const height=event.data.height;
        if(typeof height!=='number'||!Number.isFinite(height))return;
        frame.style.height=Math.max(120,Math.min(10000,Math.ceil(height)))+'px';
    });
})();
