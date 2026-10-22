const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<html><head></head><body></body></html>',{runScripts:'outside-only',url:'http://localhost/'});
const w=dom.window,requests=[],original=w.document.head.append.bind(w.document.head);
w.document.head.append=element=>{
    if(element.tagName==='SCRIPT'){
        requests.push(new URL(element.src).pathname);
        setImmediate(()=>{
            if(element.src.endsWith('/leaflet.js'))w.L={};
            else if(element.src.endsWith('/leaflet.markercluster.js'))w.L.markerClusterGroup=()=>({});
            element.dispatchEvent(new w.Event('load'));
        });
        return element;
    }
    return original(element);
};
(async()=>{
    w.eval(fs.readFileSync('meshcorestation/web/assets/aa_map_loader.js','utf8'));
    const a=w.meshcorestationLoadMapLibrary(),b=w.meshcorestationLoadMapLibrary();
    assert.strictEqual(a,b,'Parallel map opens should share one library load');
    await Promise.all([a,b]);
    assert.deepEqual(requests,['/assets/vendor/leaflet.js','/assets/vendor/leaflet.markercluster.js']);
    await w.meshcorestationLoadMapLibrary();
    assert.equal(requests.length,2,'Subsequent maps should reuse the loaded scripts');
    dom.window.close();console.log('Lazy Leaflet loading and single-flight caching passed.');
})().catch(e=>{console.error(e);process.exit(1)});
