const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const dom = new JSDOM('<html><body><button id="details"></button><section id="route-section" hidden><div id="route-summary"></div><div id="route-map"></div><div id="route-notes"></div></section><dialog id="repeaters-dialog"></dialog></body></html>', {runScripts:'outside-only',url:'http://localhost/'});
const w=dom.window;
const calls=[];
w.fetch=async url=>({ok:true,json:async()=>{calls.push(url);return {nodes:[],segments:[{positions:[[1,2],[3,4]],unresolved:true},{positions:[[3,4],[5,6]],unresolved:false}],notes:[],hops:[{number:1,name:'Hill <b>repeater</b>',hash:'aa',status:'Resolved'}],sender_name:'Alice',bot_name:'Base',direct_distance_km:12.5,route_distance_km:15.3,route_distance_lower_bound:true,path_valid:true};}});
const lines=[],arrows=[];
w.L={map:()=>({setView(){return this},remove(){},invalidateSize(){},project(p){return {x:p[1],y:-p[0]}},unproject(p){return p}}),tileLayer:()=>({on(){return this},addTo(){return this}}),polyline:(points,options)=>{lines.push(options);return {addTo(){}}},divIcon:options=>options,marker:(position,options)=>{arrows.push(options);return {addTo(){}}}};
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
        assert(!w.document.getElementById('route-hops'));
        assert.equal(lines.at(-2).color,'#ef5350');
        assert.equal(lines.at(-1).color,'#4d8eff');
        assert.equal(lines.at(-2).dashArray,'9 8');
        assert.equal(arrows.at(-1).icon.html.style.transform,'rotate(-0.7853981633974483rad)');
    }
    assert.equal(calls.length,4);
    dom.window.close(); console.log('All-command route UI and safe name rendering checks passed.');
})().catch(e=>{console.error(e);process.exit(1)});
