/* Real Leaflet overlays and chart SVGs; only remote tiles are replaced. */
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const ids=['coverage','hourly','hops','regions','neighbor-map','map-notes','missing-coordinates','ambiguous'];
const dom=new JSDOM(ids.map(id=>`<div id="statistics-${id}"></div>`).join(''),{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost'}),w=dom.window,d=w.document;
w.eval(fs.readFileSync('meshcorestation/web/assets/vendor/leaflet.js','utf8'));const L=w.L;L.Browser.svg=true;
const host=d.getElementById('statistics-neighbor-map');Object.defineProperty(host,'clientWidth',{value:800});Object.defineProperty(host,'clientHeight',{value:380});
let current,maps=0,tileError;const factory=L.map;L.map=(...args)=>{maps++;return current=factory(...args);};
L.tileLayer=()=>({on:(event,cb)=>{tileError=cb;return {addTo(){}};}});
w.meshcorestationLoadMapLibrary=async()=>{};w.requestAnimationFrame=fn=>{fn();return 1;};w.meshcorestationFormatDate=v=>'time '+v;
w.eval(fs.readFileSync('meshcorestation/web/assets/statistics_visuals.js','utf8'));
const A='aa'.repeat(32),B='bb'.repeat(32),C='cc'.repeat(32),D='dd'.repeat(32),selected={public_key:A,name:'Selected <unsafe>',latitude:49.6,longitude:8.6};
const data={selected:A,start:100,end:300,coverage_seconds:50,coverage_expected:200,excluded:2,selected_repeater:selected,
 hourly:[{at:100,receptions:3,unique_packets:2,repeated:1,unidentified:0,complete:true},{at:200,receptions:null,unique_packets:null,repeated:null,unidentified:null,complete:false},{at:300,receptions:1,unique_packets:1,repeated:0,unidentified:0,complete:false}],
 hops:[{hop_count:2,receptions:3,unique_packets:2,repeated:1,unidentified:0}],regions:[{name:'Unscoped',receptions:3,unique_packets:2,repeated:1,unidentified:0,percentage:100}],
 neighbors:[{public_key:B,name:'Two-way',latitude:49.7,longitude:8.7,incoming:2,outgoing:4,incoming_unique:2,outgoing_unique:3,last_observed:123},{public_key:C,name:'One-way',latitude:49.5,longitude:8.4,incoming:0,outgoing:2,last_observed:124},{public_key:D,name:'Missing position',latitude:null,longitude:null,incoming:1,outgoing:0,last_observed:125}],ambiguous:[{identity:'aa → bb',direction:'outgoing',receptions:2,last_observed:126,candidates:[B,C]}]};
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));};
(async()=>{try{
 w.MeshcoreStationStatisticsVisuals.render(data);await settle();assert.equal(maps,1);
 assert.equal(d.querySelectorAll('#statistics-hourly svg circle').length,6); // null unique/repeated are gaps; no false zero points
 assert(d.querySelector('#statistics-hourly circle[fill="var(--panel)"]'),'partial hours have hollow markers');
 const lines=Object.values(current._layers).filter(l=>l instanceof L.Polyline);assert.equal(lines.length,2);assert(lines.some(l=>l.options.color==='#15803d'));assert(lines.some(l=>l.options.color==='#dc2626'));
 assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,2,'actual Leaflet SVG overlays exist');
 assert.equal(Object.values(current._layers).filter(l=>l instanceof L.Marker&&l.options.icon.options.className==='route-arrow-icon').length,3);
 assert(!host.querySelector('img.leaflet-marker-icon'),'markers do not depend on image assets');
 lines[0].openPopup();assert(host.textContent.includes('4 receptions'));assert(!host.querySelector('unsafe'),'names are text, never HTML');
 assert(d.getElementById('statistics-missing-coordinates').textContent.includes('Missing position'));assert(d.getElementById('statistics-ambiguous').textContent.includes('ambiguous'));
 assert(d.getElementById('statistics-regions').textContent.includes('Unscoped'));assert(d.getElementById('statistics-regions').textContent.includes('100.0%'));
 tileError();assert(d.querySelector('.tile-warning'));assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,2);
 current.setZoom(10);current.panTo([49.6,8.6]);current.invalidateSize();assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,2);
 const old=current;w.MeshcoreStationStatisticsVisuals.render({...data,neighbors:[],ambiguous:[]});await settle();assert.notEqual(current,old);assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,0,'switch clears old connections');
 w.MeshcoreStationStatisticsVisuals.dispose();assert.equal(host.querySelectorAll('.leaflet-pane').length,0);
 const css=fs.readFileSync('meshcorestation/web/assets/zzzzz_v5.css','utf8');assert(css.includes('.statistics-chart > svg'));assert(!css.includes('#statistics-neighbor-map svg'));assert(css.includes('@media(max-width:600px)'));
 console.log('Statistics chart SVG values/gaps, Unscoped ranking, real Leaflet colors/arrows/popups, tile failure, resizing and cleanup passed.');
}finally{dom.window.close();}})().catch(e=>{console.error(e);process.exit(1);});
