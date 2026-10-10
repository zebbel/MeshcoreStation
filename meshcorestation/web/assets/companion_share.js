(() => {
    let dialog, busy = false;
    function attach() {
        const reload = document.getElementById('reload-companion');
        if (!reload || document.getElementById('share-companion')) return;
        const button = document.createElement('button');button.type = 'button';button.id = 'share-companion';button.textContent = 'Share companion (QR)';
        reload.insertAdjacentElement('afterend', button);
        button.onclick = open;
    }
    async function open() {
        if (busy) return;
        if (!dialog) {
            dialog = document.createElement('dialog');dialog.id = 'companion-share-dialog';dialog.setAttribute('aria-labelledby','companion-share-title');
            dialog.innerHTML = '<div class="dialog-header"><h2 id="companion-share-title">Share companion</h2><button type="button" aria-label="Close QR code">×</button></div><p>Scan this QR code in the MeshCore Android app to add this station as a contact.</p><p role="status"></p><div class="share-card" hidden><strong></strong><img alt="MeshCore companion contact QR code"><p class="map-key"></p><p><a class="share-open">Open in MeshCore</a> · <a class="share-download" download="meshcorestation-contact.svg">Download QR</a></p><label>Contact link<textarea readonly rows="4"></textarea></label><p class="muted">Shares the companion name and public key. This adds a contact; it does not pair your phone with the station radio.</p></div>';
            window.meshcorestationPrepareDialog(dialog);document.body.append(dialog);
            dialog.querySelector('button').onclick = () => dialog.close();
        }
        const status = dialog.querySelector('[role="status"]'), card = dialog.querySelector('.share-card');
        card.hidden = true;status.textContent = 'Reading the connected companion…';dialog.showModal();busy = true;
        try {
            const response = await fetch('/api/companion/share', {cache:'no-store',headers:{'X-Meshcore-Control':'1'}});
            const data = await response.json();if(!response.ok || !data.ok)throw Error(data.error || 'Unable to create QR code.');
            if (!dialog.open) return;
            card.querySelector('strong').textContent = data.name;
            card.querySelector('img').src = data.image;card.querySelector('.map-key').textContent = data.public_key;
            card.querySelector('.share-open').href = data.uri;card.querySelector('.share-download').href = data.image;
            card.querySelector('textarea').value = data.uri;card.hidden = false;status.textContent = '';
        } catch(error) {status.textContent = error.message;} finally {busy = false;}
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
