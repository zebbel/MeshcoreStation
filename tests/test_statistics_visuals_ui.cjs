/* Real Leaflet overlays and chart SVGs; only remote tiles are replaced. */
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const ids=['coverage','hourly','hops','regions','neighbor-map','map-notes','missing-coordinates','ambiguous'];
const dom=new JSDOM(ids.map(id=>`<div id="statistics-${id}"></div>`).join(''),{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost'}),w=dom.window,d=w.document;
w.eval(fs.readFileSync('meshcorestation/web/assets/vendor/leaflet.js','utf8'));const L=w.L;L.Browser.svg=true;
const host=d.getElementById('statistics-neighbor-map');Object.defineProperty(host,'clientWidth',{value:800});Object.defineProperty(host,'clientHeight',{value:380});
let current,maps=0,tileError;const factory=L.map;L.map=(...args)=>{maps++;return current=factory(...args);};
L.tileLayer=()=>({on:(event,cb)=>{tileError=cb;return {addTo(){}};}});
w.meshcorestationLoadMapLibrary=async()=>{};w.requestAnimationFrame=fn=>{fn();return 1;};w.meshcorestationFormatDate=v=>'time '+v;
const observers=[];w.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(target){this.target=target;}disconnect(){this.disconnected=true;}};
let chartWidth=900;Object.defineProperty(d.getElementById('statistics-hourly'),'clientWidth',{get:()=>chartWidth});
w.eval(fs.readFileSync('meshcorestation/web/assets/statistics_visuals.js','utf8'));
const A='aa'.repeat(32),B='bb'.repeat(32),C='cc'.repeat(32),D='dd'.repeat(32),selected={public_key:A,name:'Selected <unsafe>',latitude:49.6,longitude:8.6};
const data={selected:A,start:100,end:300,coverage_seconds:50,coverage_expected:200,excluded:2,selected_repeater:selected,
 hourly:[{at:100,receptions:3,unique_packets:2,repeated:1,unidentified:0,complete:true},{at:200,receptions:null,unique_packets:null,repeated:null,unidentified:null,complete:false},{at:300,receptions:1,unique_packets:1,repeated:0,unidentified:0,complete:false}],
 hops:[{hop_count:10,receptions:20,unique_packets:12,repeated:8,unidentified:0},{hop_count:2,receptions:3,unique_packets:2,repeated:1,unidentified:0},{hop_count:1,receptions:2,unique_packets:1,repeated:0,unidentified:1}],regions:[{name:'Unscoped',receptions:3,unique_packets:2,repeated:1,unidentified:0,percentage:100}],
 neighbors:[{public_key:B,name:'Two-way',latitude:49.7,longitude:8.7,incoming:2,outgoing:4,incoming_unique:2,outgoing_unique:3,last_observed:123},{public_key:C,name:'One-way',latitude:49.5,longitude:8.4,incoming:0,outgoing:2,last_observed:124},{public_key:D,name:'Missing position',latitude:null,longitude:null,incoming:1,outgoing:0,last_observed:125}],ambiguous:[{identity:'aa → bb',direction:'outgoing',receptions:2,last_observed:126,candidates:[B,C]}]};
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));};
(async()=>{try{
 w.MeshcoreStationStatisticsVisuals.render(data);await settle();assert.equal(maps,1);
 assert.equal(d.querySelectorAll('#statistics-hourly svg circle').length,0,'no scatter or gray unidentified circles');
 const hourBars=[...d.querySelectorAll('#statistics-hourly .statistics-hour-bar')];assert.equal(hourBars.length,4);
 assert(hourBars.every(bar=>['#2563eb','#c75c0d'].includes(bar.getAttribute('fill'))));
 assert(Number(hourBars[0].getAttribute('x'))<Number(hourBars[1].getAttribute('x')),'hourly series are side-by-side');
 assert(d.querySelector('#statistics-hourly .statistics-coverage-gap'),'unknown hour is a gap, never a zero');
 assert.equal(d.querySelectorAll('#statistics-hourly .statistics-incomplete').length,2,'partial counts have dashed bars');
 hourBars[0].dispatchEvent(new w.Event('click'));assert(d.querySelector('#statistics-hourly .statistics-hover-value').textContent.includes('2 unique'));
 const hopTicks=[...d.querySelectorAll('#statistics-hops .statistics-hop-tick')].map(n=>Number(n.textContent));assert.deepEqual(hopTicks,[1,2,10],'sort by numeric hop count, not traffic volume');
 const blue=d.querySelector('#statistics-hops rect[data-hop="2"][data-series="unique_packets"]'),orange=d.querySelector('#statistics-hops rect[data-hop="2"][data-series="repeated"]');
 assert.equal(blue.getAttribute('x'),orange.getAttribute('x'));assert(Math.abs(Number(orange.getAttribute('y'))+Number(orange.getAttribute('height'))-Number(blue.getAttribute('y')))<.001,'repeated orange segment stacks above unique blue');
 const hourlyDetails=d.querySelector('#statistics-hourly details');hourlyDetails.open=true;hourlyDetails.dispatchEvent(new w.Event('toggle'));assert(hourlyDetails.textContent.includes('Unidentified'));
 const hopDetails=d.querySelector('#statistics-hops details');hopDetails.open=true;hopDetails.dispatchEvent(new w.Event('toggle'));assert(hopDetails.textContent.includes('1 hop'));assert(hopDetails.textContent.includes('Unidentified'));

 const lines=Object.values(current._layers).filter(l=>l instanceof L.Polyline);assert.equal(lines.length,2);assert(lines.some(l=>l.options.color==='#15803d'));assert(lines.some(l=>l.options.color==='#dc2626'));
 assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,2,'actual Leaflet SVG overlays exist');
 assert.equal(Object.values(current._layers).filter(l=>l instanceof L.Marker&&l.options.icon.options.className==='route-arrow-icon').length,3);
 assert(!host.querySelector('img.leaflet-marker-icon'),'markers do not depend on image assets');
 const neighbor=Object.values(current._layers).find(l=>l instanceof L.Marker&&l.options.title==='Two-way');
 neighbor.fire('mouseover');assert(host.querySelector('.statistics-neighbor-tooltip').textContent.includes('We hear: 2 times'));assert(host.querySelector('.statistics-neighbor-tooltip').textContent.includes('They hear: 4 times'));
 neighbor.fire('mouseout');assert(!host.querySelector('.statistics-neighbor-tooltip'),'hover balloon closes on pointer leave');
 neighbor.fire('click',{latlng:neighbor.getLatLng()});assert(host.querySelector('.leaflet-popup-content').textContent.includes('We hear: 2 times'));assert(host.querySelector('.leaflet-popup-content').textContent.includes('They hear: 4 times'));assert(!host.querySelector('.statistics-neighbor-tooltip'),'tap/click popup does not overlap hover balloon');
 lines[0].openPopup();assert(host.textContent.includes('4 receptions'));assert(!host.querySelector('unsafe'),'names are text, never HTML');
 assert(d.getElementById('statistics-missing-coordinates').textContent.includes('Missing position'));assert(d.getElementById('statistics-ambiguous').textContent.includes('ambiguous'));
 assert(d.getElementById('statistics-regions').textContent.includes('Unscoped'));assert(d.getElementById('statistics-regions').textContent.includes('100.0%'));
 tileError();assert(d.querySelector('.tile-warning'));assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,2);
 current.setZoom(10);current.panTo([49.6,8.6]);current.invalidateSize();assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,2);
 const old=current;w.MeshcoreStationStatisticsVisuals.render({...data,neighbors:[],ambiguous:[]});await settle();assert.notEqual(current,old);assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,0,'switch clears old connections');
 for(const days of [1,7,30]){
  const hourly=Array.from({length:days*24},(_,i)=>({at:100+i*3600,receptions:null,unique_packets:null,repeated:null,unidentified:null,complete:false}));
  hourly[0]={at:100,receptions:0,unique_packets:0,repeated:0,unidentified:0,complete:true};
  hourly[1]={at:3700,receptions:2,unique_packets:0,repeated:0,unidentified:2,complete:false};
  const snapshot=JSON.stringify(hourly);
  w.MeshcoreStationStatisticsVisuals.render({...data,days,hourly});await settle();
  assert.equal(d.querySelectorAll('#statistics-hourly .statistics-coverage-gap').length,hourly.length-2);
  assert.equal(d.querySelectorAll('#statistics-hourly .statistics-confirmed-zero').length,1);
  assert.equal(d.querySelectorAll('#statistics-hourly .statistics-unplotted').length,1);
  assert.equal(d.querySelectorAll('#statistics-hourly .statistics-hour-bar').length,4,'unknown hours do not get fabricated bars');
  assert.equal(JSON.stringify(hourly),snapshot,'render does not alter saved counts');
  assert.equal(data.hops[0].hop_count,10,'numeric display sorting preserves API input order');
 }
 const chartObserver=observers.findLast(o=>o.target?.id==='statistics-hourly');
 const plot=d.querySelector('#statistics-hourly .statistics-plot-scroll');plot.scrollLeft=96;
 chartWidth=320;chartObserver.callback();
 assert.equal(d.querySelector('#statistics-hourly .statistics-plot-scroll').scrollLeft,96,'responsive redraw preserves inspected interval');
 w.MeshcoreStationStatisticsVisuals.dispose();assert(chartObserver.disconnected,'collapse cleans up chart resize observer');assert.equal(host.querySelectorAll('.leaflet-pane').length,0);
 const css=fs.readFileSync('meshcorestation/web/assets/zzzzz_v5.css','utf8');assert(css.includes('.statistics-chart > svg'));assert(!css.includes('#statistics-neighbor-map svg'));assert(css.includes('@media(max-width:600px)'));
 console.log('Statistics grouped/stacked columns, numeric hop ordering, coverage gaps, exact counts and real Leaflet hover/tap direction summaries passed.');
}finally{dom.window.close();}})().catch(e=>{console.error(e);process.exit(1);});
