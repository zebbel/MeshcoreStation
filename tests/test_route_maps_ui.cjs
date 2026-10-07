const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const dom = new JSDOM('<html><body><button id="details"></button><section id="route-section" hidden><div id="route-summary"></div><ol id="route-hops"></ol><div id="route-map"></div><div id="route-notes"></div></section><dialog id="repeaters-dialog"></dialog></body></html>', {runScripts:'outside-only',url:'http://localhost/'});
const w=dom.window;
const calls=[];
w.fetch=async url=>({ok:true,json:async()=>{calls.push(url);return {nodes:[],segments:[],notes:[],hops:[{number:1,name:'Hill <b>repeater</b>',hash:'aa',status:'Resolved'}],sender_name:'Alice',bot_name:'Base',direct_distance_km:12.5,route_distance_km:15.3,route_distance_lower_bound:true,path_valid:true};}});
w.L={map:()=>({setView(){return this},remove(){},invalidateSize(){}}),tileLayer:()=>({on(){return this},addTo(){return this}})};
w.requestAnimationFrame=fn=>fn();
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
    w.eval(fs.readFileSync('meshcorestation/web/assets/maps.js','utf8'));
    for(const [id,message] of ['status','?','scope add abc','custom'].entries()){
        const button=w.document.getElementById('details');button.dataset.details=JSON.stringify({id:id+1,message});button.click();await settle();
        assert(!w.document.getElementById('route-section').hidden);
        const summary=w.document.getElementById('route-summary');
        assert(summary.textContent.includes('Direct distance: 12.50 km'));
        assert(summary.textContent.includes('Route distance: ≥ 15.30 km'));
        assert(summary.textContent.includes('Alice → Hill <b>repeater</b> → Base'));
        assert(!summary.querySelector('b'));
        assert(w.document.getElementById('route-hops').textContent.includes('Hill'));
    }
    assert.equal(calls.length,4);
    dom.window.close(); console.log('All-command route UI and safe name rendering checks passed.');
})().catch(e=>{console.error(e);process.exit(1)});
