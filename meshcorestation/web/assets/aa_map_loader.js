/* Load core maps and discovery clustering independently, sharing concurrent opens. */
(() => {
    let core,clusters;
    function script(url){return new Promise((resolve,reject)=>{
        const element=document.createElement('script');element.src=url;
        element.onload=resolve;element.onerror=()=>{element.remove();reject(Error('Could not load '+url));};
        document.head.append(element);
    });}
    function style(url){
        if(document.querySelector('link[data-map-style="'+url+'"]'))return;
        const link=document.createElement('link');link.rel='stylesheet';link.href=url;link.dataset.mapStyle=url;document.head.append(link);
    }
    window.meshcorestationLoadMapLibrary=({clustering=false}={})=>{
        style('/assets/vendor/leaflet.css');
        if(clustering)style('/assets/vendor/MarkerCluster.css');
        if(!core)core=(window.L?Promise.resolve():script('/assets/vendor/leaflet.js'))
            .then(()=>{if(!window.L)throw Error('Leaflet did not initialize');})
            .catch(error=>{core=null;throw error;});
        if(!clustering)return core;
        if(!clusters)clusters=core.then(async()=>{
            if(!window.L.markerClusterGroup)await script('/assets/vendor/leaflet.markercluster.js');
            if(!window.L.markerClusterGroup)throw Error('Leaflet clustering did not initialize');
        }).catch(error=>{clusters=null;throw error;});
        return clusters;
    };
})();
