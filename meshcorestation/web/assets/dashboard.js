(() => {
    const {t: ui} = window.MeshcoreStationI18n || {
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`))
    };
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
            document.getElementById('detail-title').textContent = ui("Command #{0}", record.id);
            for (const [key, value] of Object.entries(record)) {
                const label = document.createElement('dt'), content = document.createElement('dd');
                const identifier = 'history.field.' + key;
                const translated = ui(identifier);
                label.textContent = translated === identifier ? key : translated;
                content.textContent = value === null ? ui("Not recorded") : value === '' ? ui('(empty)') : String(value);
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
    function historyVisibility(){
        const visible=!!document.getElementById('bot-disclosure')?.open&&!!document.getElementById('command-history-disclosure')?.open;
        window.dash_clientside?.set_props('history-visible',{data:visible});
        window.dash_clientside?.set_props('history-refresh',{disabled:!visible||document.hidden});
        if(visible&&box&&body)requestAnimationFrame(restore);
    }
    document.addEventListener('toggle',event=>{
        if(['bot-disclosure','command-history-disclosure'].includes(event.target.id))historyVisibility();
    },true);
    document.addEventListener('visibilitychange',()=>{
        window.dash_clientside?.set_props('refresh',{disabled:document.hidden});historyVisibility();
    });
    attach();
})();
