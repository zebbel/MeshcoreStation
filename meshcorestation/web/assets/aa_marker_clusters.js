/* Shared clustering for discovery maps. Packet-route hops remain unclustered. */
(() => {
    const {t: ui} = window.MeshcoreStationI18n || {
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`))
    };
    window.meshcorestationRevealMarker = (map, clusters, marker, isCurrent) => {
        const reveal = attempts => {
            if (!isCurrent()) return;
            clusters.zoomToShowLayer(marker, () => requestAnimationFrame(() => {
                if (!isCurrent()) return;
                // Reduced-motion zooms can emit moveend before the cluster's
                // zoomend cleanup. Reveal once more after that cleanup if needed.
                if (map.hasLayer(marker)) marker.openPopup();
                else if (attempts) reveal(attempts - 1);
            }));
        };
        reveal(1);
    };
    window.meshcorestationMarkerClusters = map => {
        if (!window.L?.markerClusterGroup) throw new Error(ui("Map clustering could not be loaded. Refresh the page and try again."));
        return L.markerClusterGroup({
            maxClusterRadius: 30,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            spiderfyOnMaxZoom: true,
            spiderfyDistanceMultiplier: 1.6,
            animate: !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
            iconCreateFunction(cluster) {
                const count = cluster.getChildCount();
                const badge = document.createElement('span');
                badge.textContent = count;
                badge.setAttribute('aria-label', ui("{0} repeaters. Activate to expand group.", count));
                badge.title = ui("{0} repeaters — click to expand", count);
                return L.divIcon({html: badge, className: 'repeater-cluster ' + (count < 10 ? 'cluster-small' : count < 100 ? 'cluster-medium' : 'cluster-large'), iconSize: [44, 44]});
            }
        }).addTo(map);
    };
})();
