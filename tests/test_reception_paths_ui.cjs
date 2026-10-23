const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<button id="details"></button><section id="route-section"><div id="route-summary"></div><div id="route-paths"></div><div id="route-map"></div><div id="route-notes"></div></section><dialog id="repeaters-dialog"></dialog>',{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost/'});
const w=dom.window,d=w.document;
w.eval(fs.readFileSync('meshcorestation/web/assets/vendor/leaflet.js','utf8'));
const L=w.L;L.Browser.svg=true;
Object.defineProperty(d.getElementById('route-map'),'clientWidth',{value:800});
Object.defineProperty(d.getElementById('route-map'),'clientHeight',{value:600});
let maps=0,tiles=0,fetches=0,instance;
const makeMap=L.map;
L.map=(...args)=>{maps++;return instance=makeMap(...args)};
// Keep real Leaflet routes/markers and replace only remote background tile I/O.
L.tileLayer=()=>{tiles++;return {on(){return this},addTo(){return this}}};
w.requestAnimationFrame=fn=>fn();
w.meshcorestationFormatDate=value=>'formatted '+value;
w.meshcorestationRepeaterActions=()=>{};
const sender={role:'sender',label:'Alice',position:[50,8]},bot={role:'bot',label:'Base',position:[50,9]};
function route(position,name,index,valid=true){return {
 nodes:[sender,{role:'repeater',label:name,position,order:1},bot],
 segments:[{positions:[sender.position,position]},{positions:[position,bot.position]}],
 hops:[{number:1,hash:'aa',name,status:valid?'Resolved':'Ambiguous: 2 matches'}],notes:[],
 sender_name:'Alice',bot_name:'Base',path_valid:true,direct_distance_km:71,route_distance_km:index===0?75:240,
 reception:{rssi:index===0?-100:-90,snr:3,recv_time:123+index,observations:[]}};}
const routes=[route([50.1,8.5],'Hill <b>name</b>',0),route([51,8.5],'Valley',1,false)];
w.fetch=async()=>{fetches++;return {ok:true,json:async()=>({...routes[0],reception_paths:routes})}};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 w.eval(fs.readFileSync('meshcorestation/web/assets/maps.js','utf8'));
 const engine=w.L;delete w.L;let ready;
 w.meshcorestationLoadMapLibrary=()=>new Promise(resolve=>ready=()=>{w.L=engine;resolve()});
 const details=d.getElementById('details');details.dataset.details=JSON.stringify({id:1});details.click();await settle();
 const buttons=d.querySelectorAll('#route-paths button');
 assert.equal(buttons.length,2);assert.equal(buttons[0].getAttribute('aria-pressed'),'true');
 assert(buttons[0].textContent.includes('RSSI -100 dBm'));assert(buttons[0].textContent.includes('SNR 3 dB'));assert(buttons[0].textContent.includes('formatted 123'));
 assert(buttons[1].textContent.includes('Ambiguous: 2 matches'));
 // Selection must work even while the map library is loading.
 buttons[1].click();assert(d.getElementById('route-summary').textContent.includes('240.00 km'));
 ready();await settle();
 assert.equal(maps,1);assert.equal(tiles,1);
 const endpoints=Object.values(instance._layers).filter(layer=>layer.options.title?.startsWith('sender:')||layer.options.title?.startsWith('bot:'));
 assert.equal(endpoints.length,2);
 const center=instance.getCenter(),zoom=instance.getZoom();
 const initialLayers=Object.values(instance._layers).length;
 const initialArrow=Object.values(instance._layers).find(layer=>layer.options.icon?.options.className==='route-arrow-icon').options.icon.options.html.style.transform;
 for(let i=0;i<5;i++){
  buttons[0].click();
  assert(d.getElementById('route-summary').textContent.includes('75.00 km'));
  assert(d.getElementById('route-summary').textContent.includes('Hill <b>name</b>'));
  assert(!d.getElementById('route-summary').querySelector('b'));
  assert.equal(buttons[0].getAttribute('aria-pressed'),'true');
  assert.equal(buttons[1].getAttribute('aria-pressed'),'false');
  assert(Object.values(instance._layers).some(layer=>layer.options.title==='repeater: Hill <b>name</b>'));
  assert(!Object.values(instance._layers).some(layer=>layer.options.title==='repeater: Valley'));
  const line=Object.values(instance._layers).find(layer=>layer instanceof L.Polyline);
  assert.equal(line.getLatLngs()[1].lat,50.1);
  const arrow=Object.values(instance._layers).find(layer=>layer.options.icon?.options.className==='route-arrow-icon');
  assert(arrow.options.icon.options.html.style.transform.startsWith('rotate('));
  assert.notEqual(arrow.options.icon.options.html.style.transform,initialArrow,'Path selection must update arrow direction');
  buttons[1].click();
 }
 assert.equal(Object.values(instance._layers).length,initialLayers,'Switching must remove all old overlays');
 assert(endpoints.every(layer=>instance.hasLayer(layer)),'Sender and bot markers must stay in place');
 assert(instance.getCenter().equals(center));assert.equal(instance.getZoom(),zoom);
 assert.equal(maps,1);assert.equal(tiles,1);assert.equal(fetches,1);
 assert(d.querySelector('#route-notes .map-legend'));
 d.getElementById('route-section').closest('body').append(Object.assign(d.createElement('dialog'),{id:'details-dialog'}));
 d.getElementById('details-dialog').dispatchEvent(new w.Event('close'));
 assert.equal(Object.keys(instance._layers).length,0);
 dom.window.close();console.log('Real Leaflet path selection: metrics, loading race, routes/arrows, fixed endpoints, map/tile reuse and cleanup passed.');
})().catch(error=>{console.error(error);dom.window.close();process.exit(1)});
