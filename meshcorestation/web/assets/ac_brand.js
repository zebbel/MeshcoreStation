/* Use the locally cached official icon; show the existing initial if it is unavailable. */
(() => {
    document.addEventListener('error', event => {
        if (event.target.id === 'meshcore-brand-image') {
            event.target.hidden = true;
            const fallback = document.getElementById('brand-fallback'); if (fallback) fallback.hidden = false;
        }
    }, true);
})();
