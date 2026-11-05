/* Real Leaflet overlays and chart SVGs; only remote tiles are replaced. */
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const ids=['neighbor-snr','active-neighbors','heatmap','packet-types','coverage','hourly','hops','regions','neighbor-map','map-notes','missing-coordinates','ambiguous'];
const dom=new JSDOM(ids.map(id=>`<div id="statistics-${id}"></div>`).join(''),{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost'}),w=dom.window,d=w.document;
w.eval(fs.readFileSync('meshcorestation/web/assets/vendor/leaflet.js','utf8'));const L=w.L;L.Browser.svg=true;
const host=d.getElementById('statistics-neighbor-map');let mapWidth=800;Object.defineProperty(host,'clientWidth',{get:()=>mapWidth});Object.defineProperty(host,'clientHeight',{value:380});
let current,maps=0,tileError;const factory=L.map;L.map=(...args)=>{maps++;return current=factory(...args);};
L.tileLayer=()=>({on:(event,cb)=>{tileError=cb;return {addTo(){}};}});
w.meshcorestationLoadMapLibrary=async()=>{};w.requestAnimationFrame=fn=>{fn();return 1;};w.meshcorestationFormatDate=v=>'time '+v;
const observers=[];w.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(target){this.target=target;}disconnect(){this.disconnected=true;}};
let chartWidth=900;Object.defineProperty(d.getElementById('statistics-hourly'),'clientWidth',{get:()=>chartWidth});
w.eval(fs.readFileSync('meshcorestation/web/assets/statistics_visuals.js','utf8'));
const A='aa'.repeat(32),B='bb'.repeat(32),C='cc'.repeat(32),D='dd'.repeat(32),selected={public_key:A,name:'Selected <unsafe>',latitude:49.6,longitude:8.6};
const data={selected:A,start:100,end:300,coverage_seconds:50,coverage_expected:200,excluded:2,selected_repeater:selected,
 activity_hourly:[{at:1793487600,receptions:3,unique_packets:2,repeated:1,complete:true,expected_seconds:3600,coverage_seconds:3600},{at:1793491200,receptions:null,complete:false,expected_seconds:3600,coverage_seconds:0},{at:1793494800,receptions:0,complete:true,expected_seconds:3600,coverage_seconds:3600},{at:1793498400,receptions:2,complete:false,expected_seconds:3600,coverage_seconds:100}],
 neighbor_snr:[{public_key:B,name:'Two-way',prefix:'bbbb',resolution:'matched',average_snr:3.75,samples:2,last_heard:100},{public_key:null,prefix:'ffff',resolution:'unknown',average_snr:1,samples:1,last_heard:100}],
 packet_types:[{category:'Group messages',evidence:'observed-flood-route',receptions:3,unique_packets:2,repeated:1,unidentified:0,percentage:75},{category:'Advertisements',evidence:'advertisement-origin',receptions:1,unique_packets:1,repeated:0,unidentified:0,percentage:25}],
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
 assert(Number(blue.getAttribute('x'))<Number(orange.getAttribute('x')),'hop bars are grouped side-by-side');assert.equal(Number(blue.getAttribute('y'))+Number(blue.getAttribute('height')),Number(orange.getAttribute('y'))+Number(orange.getAttribute('height')),'grouped bars share the baseline');
 const hourlyDetails=d.querySelector('#statistics-hourly details');hourlyDetails.open=true;hourlyDetails.dispatchEvent(new w.Event('toggle'));assert(hourlyDetails.textContent.includes('Unidentified'));
 const hopDetails=d.querySelector('#statistics-hops details');hopDetails.open=true;hopDetails.dispatchEvent(new w.Event('toggle'));assert(hopDetails.textContent.includes('1 hop'));assert(hopDetails.textContent.includes('Unidentified'));

 assert(d.querySelector('#statistics-neighbor-snr').textContent.includes('3.75 dB'));assert(d.querySelector('#statistics-neighbor-snr').textContent.includes('Unknown Repeater (ffff…)'));assert(d.querySelector('#statistics-neighbor-snr').textContent.includes('single sample'));
 const active=[...d.querySelectorAll('#statistics-active-neighbors .statistics-neighbor-bar')];assert.equal(active.length,6);assert.equal(active[0].dataset.key,B);assert.equal(active[0].dataset.direction,'incoming');assert.equal(active[1].dataset.value,'4');assert(active.some(n=>n.dataset.key===D),'missing coordinates do not exclude active neighbors');
 const cells=[...d.querySelectorAll('.statistics-heatmap-cell')];assert(cells.some(n=>n.dataset.state==='unknown'&&n.dataset.count===''));assert(cells.some(n=>n.dataset.state==='complete'&&n.dataset.count==='0'));assert(cells.some(n=>n.dataset.state==='incomplete'&&n.dataset.count==='2'));cells.find(n=>n.dataset.count==='3').dispatchEvent(new w.Event('click'));assert(d.querySelector('#statistics-heatmap .statistics-hover-value').textContent.includes('3 observed receptions'));
 const donut=[...d.querySelectorAll('.statistics-donut-segment')];assert.equal(donut.length,2);assert.equal(donut[0].dataset.count,'3');donut[1].dispatchEvent(new w.Event('click'));assert(d.querySelector('#statistics-packet-types .statistics-hover-value').textContent.includes('Advertisement origin (not forwarding)'));assert(d.querySelector('#statistics-packet-types .statistics-hover-value').textContent.includes('25.0%'));
 const lines=Object.values(current._layers).filter(l=>l instanceof L.Polyline);assert.equal(lines.length,2);assert(lines.some(l=>l.options.color==='#15803d'));assert(lines.some(l=>l.options.color==='#dc2626'));
 assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,2,'actual Leaflet SVG overlays exist');
 assert.equal(Object.values(current._layers).filter(l=>l instanceof L.Marker&&l.options.icon.options.className.split(' ').includes('route-arrow-icon')).length,3);
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
 // Regional counting modes use existing digest-based counts, never a refetch.
 const regional=[{name:'Alpha',receptions:20,unique_packets:5,repeated:15,unidentified:0},{name:'Beta',receptions:12,unique_packets:10,repeated:2,unidentified:0},{name:'Unscoped',receptions:6,unique_packets:4,repeated:2,unidentified:0}];
 const regionalSource=JSON.stringify(regional);
 w.MeshcoreStationStatisticsVisuals.render({...data,regions:regional});await settle();
 let regionBars=[...d.querySelectorAll('.statistics-region-bar')];
 assert.equal(regionBars.length,6);
 assert.deepEqual(regionBars.filter(r=>r.dataset.series==='unique_packets').map(r=>r.dataset.name),['Beta','Alpha','Unscoped']);
 assert.deepEqual(regionBars.filter(r=>r.dataset.series==='unique_packets').map(r=>r.dataset.count),['10','5','4']);
 assert.equal(regionBars[0].dataset.mode,'unique');assert(Math.abs(Number(regionBars[0].dataset.percentage)-1000/19)<1e-9);
 assert.deepEqual(regionBars.filter(r=>r.dataset.series==='unique_packets').map(r=>r.getAttribute('fill')),['#2563eb','#2563eb','#2563eb']);
 const repeatedBars=regionBars.filter(r=>r.dataset.series==='repeated');
 assert.equal(repeatedBars.length,3);assert(repeatedBars.every(r=>r.getAttribute('fill')==='#c75c0d'&&Number(r.getAttribute('width'))>0),'repeated receptions remain visible in unique ranking mode');
 for(const name of ['Alpha','Beta','Unscoped']){
  const bars=regionBars.filter(r=>r.dataset.name===name),[unique,repeated]=bars;
  assert.equal(unique.dataset.series,'unique_packets');assert.equal(repeated.dataset.series,'repeated');
  assert.equal(unique.getAttribute('x'),repeated.getAttribute('x'));assert(Number(unique.getAttribute('y'))+Number(unique.getAttribute('height'))<Number(repeated.getAttribute('y')));
  assert(Math.abs(Number(unique.getAttribute('width'))/Number(unique.dataset.value)-Number(repeated.getAttribute('width'))/Number(repeated.dataset.value))<1e-9,'both bars share one scale');
 }
 const initialWidths=new Map(regionBars.map(r=>[r.dataset.name+'|'+r.dataset.series,r.getAttribute('width')]));
 repeatedBars[0].dispatchEvent(new w.Event('focus'));assert(d.querySelector('#statistics-regions .statistics-hover-value').textContent.includes('12 total observed receptions'));
 repeatedBars[0].dispatchEvent(new w.Event('click'));assert(d.querySelector('#statistics-regions .statistics-hover-value').textContent.includes('2 repeated receptions'));

 const mapCount=maps,otherChart=d.getElementById('statistics-hourly').innerHTML;
 let external=0;w.fetch=()=>{external++;throw Error('Unexpected request');};
 let all=d.getElementById('statistics-regions-all');assert(!all.checked);all.checked=true;all.dispatchEvent(new w.Event('change'));
 regionBars=[...d.querySelectorAll('.statistics-region-bar')];
 assert.deepEqual(regionBars.filter(r=>r.dataset.series==='unique_packets').map(r=>r.dataset.name),['Alpha','Beta','Unscoped']);
 assert.equal(regionBars[0].dataset.count,'20');assert(Math.abs(Number(regionBars[0].dataset.percentage)-2000/38)<1e-9);
 assert.equal(regionBars.length,6);assert(regionBars.filter(r=>r.dataset.series==='repeated').every(r=>r.getAttribute('fill')==='#c75c0d'));
 for(const r of regionBars)assert.equal(r.getAttribute('width'),initialWidths.get(r.dataset.name+'|'+r.dataset.series),'ranking mode does not change either bar count/scale');
 assert.equal(external,0);assert.equal(maps,mapCount);assert.equal(d.getElementById('statistics-hourly').innerHTML,otherChart);
 for(const days of [1,7,30]){w.MeshcoreStationStatisticsVisuals.render({...data,days,selected:B,regions:regional});await settle();assert(d.getElementById('statistics-regions-all').checked);assert.equal(d.querySelector('.statistics-region-value').firstChild.textContent,'20 · 52.6%');}
 all=d.getElementById('statistics-regions-all');all.checked=false;all.dispatchEvent(new w.Event('change'));
 assert.equal(d.querySelector('.statistics-region-value').firstChild.textContent,'10 · 52.6%');assert.equal(JSON.stringify(regional),regionalSource);
 // Donut and legend order aggregate origins/floods by code, with stable code ties.
 const types=[{packet_type:15,evidence:'observed-flood-route',receptions:20,unique_packets:10,repeated:10,unidentified:0},{packet_type:0,evidence:'observed-flood-route',receptions:2,unique_packets:2,repeated:0,unidentified:0},{packet_type:4,evidence:'advertisement-origin',receptions:8,unique_packets:8,repeated:0,unidentified:0},{packet_type:5,evidence:'observed-flood-route',receptions:20,unique_packets:20,repeated:0,unidentified:0},{packet_type:4,evidence:'observed-flood-route',receptions:2,unique_packets:2,repeated:0,unidentified:0}];
 for(const r of types)r.percentage=100*r.receptions/52;
 const typeSource=JSON.stringify(types);
 w.MeshcoreStationStatisticsVisuals.render({...data,packet_types:types});await settle();
 assert.deepEqual([...d.querySelectorAll('.statistics-donut-segment')].map(r=>r.dataset.category),['5','15','4','0']);
 assert.deepEqual([...d.querySelectorAll('.statistics-packet-category strong')].map(r=>r.textContent),['Group text message','Raw custom packet','Advertisement','Request']);
 assert.deepEqual([...d.querySelectorAll('.statistics-donut-segment')].map(r=>r.getAttribute('stroke')),['#0891b2','#0284c7','#be185d','#2563eb']);
 assert(d.getElementById('statistics-packet-types').textContent.includes('Origin (not forwarding): 8 · Flood path: 2'));
 const changed=types.map(r=>r.packet_type===0?{...r,receptions:50}:r);
 w.MeshcoreStationStatisticsVisuals.render({...data,packet_types:changed});await settle();
 assert.equal(d.querySelector('.statistics-donut-segment').dataset.category,'0');assert.equal(d.querySelector('.statistics-packet-category strong').textContent,'Request');assert.equal(JSON.stringify(types),typeSource);
 // At least 20 distinct traffic colors; scale is continuous, adaptive, and preserves exact counts.
 const begin=Date.parse('2026-11-01T00:00:00Z')/1000;
 const activity=Array.from({length:40},(_,i)=>({at:begin+i*3600,until:begin+(i+1)*3600,receptions:i+1,complete:true,coverage_seconds:3600,expected_seconds:3600}));
 const activitySource=JSON.stringify(activity);
 w.MeshcoreStationStatisticsVisuals.render({...data,start:begin,end:begin+40*3600,activity_hourly:activity});await settle();
 const measured=[...d.querySelectorAll('.statistics-heatmap-cell')].filter(r=>Number(r.dataset.count)>0);
 assert.equal(measured.length,40);assert(new Set(measured.map(r=>r.getAttribute('fill'))).size>=20);
 assert.deepEqual(measured.map(r=>Number(r.dataset.count)),activity.map(r=>r.receptions));
 const firstColor=measured[0].getAttribute('fill');assert(d.querySelector('.statistics-heatmap-ramp').style.background.includes('linear-gradient'));
 w.MeshcoreStationStatisticsVisuals.render({...data,start:begin,end:begin+40*3600,activity_hourly:activity.map(r=>({...r,receptions:r.receptions*2}))});await settle();
 assert.equal(d.querySelector('.statistics-heatmap-cell[data-count="2"]').getAttribute('fill'),firstColor,'color domain adapts to the current period maximum');assert.equal(JSON.stringify(activity),activitySource);
 w.MeshcoreStationStatisticsVisuals.render(data);await settle();
 const many=Array.from({length:24},(_,i)=>({public_key:String(i).padStart(64,'0'),name:'Neighbor '+i,incoming:i,outgoing:2*i,last_observed:100}));
 w.MeshcoreStationStatisticsVisuals.render({...data,neighbors:many,activity_hourly:[],packet_types:[]});await settle();
 const top=[...d.querySelectorAll('#statistics-active-neighbors .statistics-neighbor-bar')];assert.equal(top.length,40);assert.equal(top[0].dataset.value,'23');assert.equal(top[1].dataset.value,'46');assert(d.querySelector('#statistics-heatmap').textContent.includes('No saved activity'));assert(d.querySelector('#statistics-packet-types').textContent.includes('No confidently attributed'));
 const foldStart=Date.parse('2026-10-25T00:00:00Z')/1000;
 const folds=[0,1].map((offset)=>({at:foldStart+offset*3600,until:foldStart+(offset+1)*3600,receptions:offset+1,complete:true,coverage_seconds:3600,expected_seconds:3600}));
 w.MeshcoreStationStatisticsVisuals.render({...data,activity_timezone:'Europe/Berlin',activity_hourly:folds});await settle();
 const folded=d.querySelector('.statistics-heatmap-cell[data-day="2026-10-25"][data-hour="2"]');assert.equal(folded.dataset.count,'3');folded.dispatchEvent(new w.Event('click'));assert(d.querySelector('#statistics-heatmap .statistics-hover-value').textContent.includes('Repeated clock hour'));
 w.MeshcoreStationStatisticsVisuals.stale();assert(d.querySelector('#statistics-heatmap').classList.contains('statistics-stale'));assert(d.querySelector('#statistics-packet-types').classList.contains('statistics-stale'));
 w.MeshcoreStationStatisticsVisuals.render(data);await settle();assert(!d.querySelector('#statistics-heatmap').classList.contains('statistics-stale'));
 mapWidth=0;w.MeshcoreStationStatisticsVisuals.render(data);await settle();assert(!d.querySelector('#statistics-map-notes').textContent.includes('Map unavailable'),'hidden map initialization must use a finite view');
 mapWidth=800;w.MeshcoreStationStatisticsVisuals.resize();await settle();assert(Number.isFinite(current.getZoom()));assert.equal(host.querySelectorAll('svg path.leaflet-interactive').length,2,'opening a hidden map redraws actual relationship overlays');
 const chartObserver=observers.findLast(o=>o.target?.id==='statistics-hourly');
 const plot=d.querySelector('#statistics-hourly .statistics-plot-scroll');plot.scrollLeft=96;
 chartWidth=320;chartObserver.callback();
 assert.equal(d.querySelector('#statistics-hourly .statistics-plot-scroll').scrollLeft,96,'responsive redraw preserves inspected interval');
 w.MeshcoreStationStatisticsVisuals.dispose();assert(chartObserver.disconnected,'collapse cleans up chart resize observer');assert.equal(host.querySelectorAll('.leaflet-pane').length,0);
 const css=fs.readFileSync('meshcorestation/web/assets/zzzzz_v5.css','utf8');assert(css.includes('.statistics-chart > svg'));assert(!css.includes('#statistics-neighbor-map svg'));assert(css.includes('@media(max-width:600px)'));
 const summaryCSS=fs.readFileSync('meshcorestation/web/assets/repeater_statistics.css','utf8');assert(summaryCSS.includes('text-overflow:ellipsis'));assert(summaryCSS.includes('justify-content:space-between'));
 console.log('Statistics tooltip rows, grouped columns, neighbor ranking, heatmap, donut, numeric hop ordering, coverage gaps, exact counts and real Leaflet hover/tap direction summaries passed.');
}finally{dom.window.close();}})().catch(e=>{console.error(e);process.exit(1);});
