/* Await both scripts and styles; failed or stalled assets can be retried. */
(() => {
    let core, clusters;
    const styles = new Map(), scripts = new Map();
    function asset(url, stylesheet = false) {
        return new Promise((resolve, reject) => {
            const element = document.createElement(stylesheet ? 'link' : 'script');
            if (stylesheet) { element.rel = 'stylesheet'; element.href = url; element.dataset.mapStyle = url; }
            else element.src = url;
            const finish = error => {
                clearTimeout(timer);
                element.onload = element.onerror = null;
                if (error) { element.remove(); reject(error); }
                else resolve();
            };
            const timer = setTimeout(() => finish(Error('Timed out loading map asset: ' + url)), 15000);
            element.onload = () => finish();
            element.onerror = () => finish(Error('Could not load map asset: ' + url));
            document.head.append(element);
        });
    }
    function script(url) {
        if (!scripts.has(url)) scripts.set(url, asset(url).catch(error => { scripts.delete(url); throw error; }));
        return scripts.get(url);
    }
    function style(url) {
        if (!styles.has(url)) styles.set(url, asset(url, true).catch(error => { styles.delete(url); throw error; }));
        return styles.get(url);
    }
    window.meshcorestationLoadMapLibrary = ({clustering = false} = {}) => {
        if (!core) core = Promise.all([
            style('/assets/vendor/leaflet.css'),
            window.L ? Promise.resolve() : script('/assets/vendor/leaflet.js')
        ]).then(() => {
            if (!window.L?.map) throw Error('Leaflet did not initialize. Reload the page and try again.');
        }).catch(error => { core = null; throw error; });
        if (!clustering) return core;
        if (!clusters) clusters = Promise.all([core, style('/assets/vendor/MarkerCluster.css')]).then(async () => {
            if (!window.L.markerClusterGroup) await script('/assets/vendor/leaflet.markercluster.js');
            if (!window.L.markerClusterGroup) throw Error('Leaflet clustering did not initialize. Reload the page and try again.');
        }).catch(error => { clusters = null; throw error; });
        return clusters;
    };
})();
