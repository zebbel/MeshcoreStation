const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<html><head></head><body></body></html>',{runScripts:'outside-only',url:'http://localhost/'});
const w=dom.window,requests=[],styles=[],original=w.document.head.append.bind(w.document.head);
w.document.head.append=element=>{
    if(element.tagName==='SCRIPT'){
        requests.push(new URL(element.src).pathname);
        setImmediate(()=>{
            if(element.src.endsWith('/leaflet.js'))w.L={map(){}};
            else if(element.src.endsWith('/leaflet.markercluster.js'))w.L.markerClusterGroup=()=>({});
            element.dispatchEvent(new w.Event('load'));
        });
        return element;
    }
    const result=original(element);
    if(element.tagName==='LINK') {
        styles.push(element);
        if(styles.length>1)setImmediate(()=>element.dispatchEvent(new w.Event('load')));
    }
    return result;
};
(async()=>{
    w.eval(fs.readFileSync('meshcorestation/web/assets/aa_map_loader.js','utf8'));
    const a=w.meshcorestationLoadMapLibrary(),b=w.meshcorestationLoadMapLibrary();
    assert.strictEqual(a,b,'Parallel route opens should share core loading');
    let loaded=false;a.then(()=>loaded=true);
    await new Promise(resolve=>setImmediate(resolve));
    assert(!loaded,'Leaflet must wait for its CSS, even after the script loads');
    styles[0].dispatchEvent(new w.Event('load'));
    await Promise.all([a,b]);
    assert.deepEqual(requests,['/assets/vendor/leaflet.js'],'Route maps must not load clustering');
    await w.meshcorestationLoadMapLibrary({clustering:true});
    assert.deepEqual(requests,['/assets/vendor/leaflet.js','/assets/vendor/leaflet.markercluster.js']);
    await w.meshcorestationLoadMapLibrary({clustering:true});
    assert.equal(requests.length,2);
    dom.window.close();console.log('Lazy Leaflet loading and single-flight caching passed.');
})().catch(e=>{console.error(e);process.exit(1)});
