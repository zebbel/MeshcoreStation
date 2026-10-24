/* Actual bundled Leaflet builds SVG paths and divIcon DOM, rather than stubbing polyline. */
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const fixture='tests/fixtures/analyzer/responses/',files={detail:'node_detail_24h.json',neighbors:'node_neighbors.json',reach:'node_reach_1d.json',metrics:'graph_metrics.json',clock:'clock_skew_24h.json',direct:'direct_packets_24h_empty.json',beacons:'channel_beacons_720h_empty.json',sensors:'channel_sensors_720h_empty.json'};
const data=Object.fromEntries(Object.entries(files).map(([name,file])=>[name,JSON.parse(fs.readFileSync(fixture+file))]));
const css=['style.css','repeater_statistics.css','network_monitoring.css'].map(n=>fs.readFileSync('meshcorestation/web/assets/'+n,'utf8')).join('\n');
const dom=new JSDOM('<style>'+css+'</style><details id="repeater-optimizer-disclosure" open><summary>Optimizer</summary><details id="repeater-network-disclosure" open><summary>Network</summary><button id="network-refresh"></button><p id="network-status"></p><div id="network-content"></div></details></details>',{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window;
Object.defineProperty(w.HTMLElement.prototype,'clientWidth',{get(){return this.classList.contains('network-map')?800:0}});Object.defineProperty(w.HTMLElement.prototype,'clientHeight',{get(){return this.classList.contains('network-map')?400:0}});
w.eval(fs.readFileSync('meshcorestation/web/assets/vendor/leaflet.js','utf8'));w.L.Browser.svg=true;
const maps=[],create=w.L.map;w.L.map=(host,options)=>{const map=create(host,{...options,zoomAnimation:false,fadeAnimation:false});maps.push(map);return map;};
w.meshcorestationLoadMapLibrary=async()=>{};w.meshcorestationSelectedRepeater=data.detail.node.id;w.meshcorestationFormatDate=String;w.AbortController=AbortController;
w.fetch=async()=>({ok:true,json:async()=>({ok:true,public_key:data.detail.node.id,state:'available',stale:false,data,fetched_at:1})});
const wait=()=>new Promise(r=>setTimeout(r,40));
async function settled(){let previous=-1;for(let i=0;i<15;i++){await wait();if(maps.length===previous&&maps.at(-1)?._mapPane)return;previous=maps.length;}throw Error('Map did not settle');}
(async()=>{
 for(const file of ['ab_repeater_names.js','network_monitoring.js'])w.eval(fs.readFileSync('meshcorestation/web/assets/'+file,'utf8'));
 await settled();const doc=w.document,paths=doc.querySelectorAll('path.network-relationship');assert(paths.length>0);
 assert([...paths].every(p=>p.getAttribute('d').includes('L')&&p.getAttribute('stroke-dasharray')),'Leaflet projected actual line geometry');
 const svg=paths[0].parentNode.parentNode;
 assert.notEqual(w.getComputedStyle(svg).maxHeight,'210px');assert.notEqual(w.getComputedStyle(svg).minHeight,'170px');
 assert.equal(doc.querySelectorAll('.network-map img.leaflet-marker-icon').length,0);assert.equal(doc.querySelectorAll('.network-map .leaflet-marker-icon').length,1+data.reach.neighbourList.filter(n=>typeof n.lat==='number'&&typeof n.lon==='number').length);
 const active=maps.at(-1),before=paths[0].getAttribute('d');active.setZoom(12);await wait();assert.notEqual(paths[0].getAttribute('d'),before);
 const center=active.getCenter();active.panBy([50,20],{animate:false});assert(!center.equals(active.getCenter()));
 const section=doc.getElementById('repeater-network-disclosure');section.open=false;section.dispatchEvent(new w.Event('toggle'));await wait();assert.equal(doc.querySelectorAll('path.network-relationship').length,0);
 section.open=true;section.dispatchEvent(new w.Event('toggle'));await wait();assert.equal(doc.querySelectorAll('.network-map.leaflet-container').length,1);
 assert.equal(doc.querySelectorAll('path.network-relationship').length,paths.length);dom.window.close();console.log('Bundled Leaflet SVG DOM: projected dashed paths, CSS isolation, image-free markers, zoom, pan and reopen passed.');
})().catch(e=>{console.error(e);process.exit(1)});
