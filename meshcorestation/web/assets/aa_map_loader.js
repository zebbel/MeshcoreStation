/* Load the 180 kB map engine only on the first map request, not during dashboard boot. */
(() => {
    let pending;
    function script(url) {
        return new Promise((resolve, reject) => {
            const element = document.createElement('script');
            element.src = url;
            element.onload = resolve;
            element.onerror = () => { element.remove(); reject(new Error('Could not load ' + url)); };
            document.head.append(element);
        });
    }
    // Pre-fetch during browser idle without executing Leaflet until a map is requested.
    // This makes the first map faster while leaving the initial dashboard responsive.
    window.addEventListener('load', () => {
        const warmCache = () => {
            if (window.L) return;
            for (const url of ['/assets/vendor/leaflet.js', '/assets/vendor/leaflet.markercluster.js']) {
                const link = document.createElement('link');
                link.rel = 'prefetch'; link.as = 'script'; link.href = url;
                document.head.append(link);
            }
        };
        if (window.requestIdleCallback) window.requestIdleCallback(warmCache);
    }, {once: true});
    window.meshcorestationLoadMapLibrary = () => {
        if (window.L?.markerClusterGroup) return Promise.resolve();
        if (!pending) {
            pending = (async () => {
                if (!window.L) await script('/assets/vendor/leaflet.js');
                if (!window.L?.markerClusterGroup) await script('/assets/vendor/leaflet.markercluster.js');
                if (!window.L?.markerClusterGroup) throw new Error('Leaflet clustering did not initialize');
            })().catch(error => { pending = null; throw error; });
        }
        return pending;
    };
})();
