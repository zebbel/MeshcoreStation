(() => {
    let box, body, initial = true, follow = true, anchor = null, anchorOffset = 0, previousFilter, frame;
    function remember() {
        if (document.getElementById('command-history-disclosure')?.open === false) return;
        follow = box.scrollHeight - box.clientHeight - box.scrollTop < 40;
        const top = box.getBoundingClientRect().top + 42;
        const row = [...body.querySelectorAll('[data-row-id]')].find(r => r.getBoundingClientRect().bottom > top);
        anchor = row ? row.dataset.rowId : null;
        anchorOffset = row ? row.getBoundingClientRect().top - box.getBoundingClientRect().top : 0;
    }
    function restore() {
        if (document.getElementById('command-history-disclosure')?.open === false) return;
        const filter = body.dataset.filter;
        if (initial || filter !== previousFilter || follow) { box.scrollTop = box.scrollHeight; }
        else if (anchor) {
            const row = [...body.querySelectorAll('[data-row-id]')].find(r => r.dataset.rowId === anchor);
            if (row) box.scrollTop += row.getBoundingClientRect().top - box.getBoundingClientRect().top - anchorOffset;
        }
        initial = !body.querySelector('[data-row-id]');
        previousFilter = filter;
        remember();
    }
    function attach() {
        box = document.getElementById('command-scroll');
        body = document.getElementById('command-rows');
        if (!box || !body) return;
        observer.disconnect();
        box.addEventListener('scroll', remember, { passive: true });
        new MutationObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(restore); }).observe(body, { childList: true, subtree: true, attributes: true });
        restore();
    }
    const observer = new MutationObserver(attach);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    document.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (button?.id === 'open-commands') { event.preventDefault(); }
        const dialog = document.getElementById('details-dialog');
        if (button && button.dataset.details) {
            const record = JSON.parse(button.dataset.details), fields = document.getElementById('detail-fields');
            fields.replaceChildren();
            document.getElementById('detail-title').textContent = `Command #${record.id}`;
            for (const [key, value] of Object.entries(record)) {
                const label = document.createElement('dt'), content = document.createElement('dd');
                label.textContent = key;
                content.textContent = value === null ? 'Not recorded' : value === '' ? '(empty)' : String(value);
                fields.append(label, content);
            }
            dialog.showModal();
            document.getElementById('close-details').focus();
        }
        if (button && button.id === 'close-details') dialog.close();
        if (button && button.id === 'jump-latest') { box.scrollTop = box.scrollHeight; remember(); }
        if (event.target === dialog) {
            const rect = dialog.getBoundingClientRect();
            if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
        }
    });
    document.addEventListener('toggle', event => {
        if(event.target.id==='command-history-disclosure'){
            window.dash_clientside?.set_props('history-visible',{data:event.target.open});
            window.dash_clientside?.set_props('history-refresh',{disabled:!event.target.open||document.hidden});
        }
        if(event.target.id==='room-server-disclosure'){
            document.getElementById('room-server-frame')?.contentWindow?.postMessage({kind:'meshcorestation-room-visible',visible:event.target.open},location.origin);
        }
        if (event.target.id === 'room-server-disclosure' && event.target.open) {
            const iframe = document.getElementById('room-server-frame');
            if (iframe?.dataset.src) { iframe.src = iframe.dataset.src; delete iframe.dataset.src; }
        }
        if (event.target.id === 'command-history-disclosure' && event.target.open && box && body) requestAnimationFrame(restore);
    }, true);
    document.addEventListener('visibilitychange',()=>{
        window.dash_clientside?.set_props('refresh',{disabled:document.hidden});
        window.dash_clientside?.set_props('history-refresh',{disabled:document.hidden||!document.getElementById('command-history-disclosure')?.open});
    });
    attach();
})();
