const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const manifest=JSON.parse(fs.readFileSync('tests/fixtures/analyzer/manifest.json'));
const key=manifest.repeater_public_key,other='ab'.repeat(32);
const names={detail:'node_detail_24h.json',neighbors:'node_neighbors.json',reach:'node_reach_1d.json',metrics:'graph_metrics.json',clock:'clock_skew_24h.json',direct:'direct_packets_24h_empty.json',beacons:'channel_beacons_720h_empty.json',sensors:'channel_sensors_720h_empty.json'};
const data=Object.fromEntries(Object.entries(names).map(([k,v])=>[k,JSON.parse(fs.readFileSync('tests/fixtures/analyzer/responses/'+v))]));
const dom=new JSDOM('<body><details id="repeater-optimizer-disclosure"><summary>Optimizer</summary><details id="repeater-network-disclosure"><summary>Network</summary><button id="network-refresh">Refresh</button><p id="network-status"></p><div id="network-content"></div></details></details></body>',{url:'http://localhost',runScripts:'outside-only'}),w=dom.window,$=id=>w.document.getElementById(id);
w.AbortController=AbortController;w.meshcorestationSelectedRepeater=key;w.meshcorestationFormatDate=v=>'DATE:'+v;
w.setInterval=()=>{throw Error('No background polling permitted')};
const maps=[];w.meshcorestationLoadMapLibrary=async o=>{assert.equal(o.clustering,false)};
w.requestAnimationFrame=fn=>w.setTimeout(fn,0);w.cancelAnimationFrame=w.clearTimeout;
w.L={divIcon:o=>o,map:(host,options)=>{assert.equal(options.maxZoom,19);const m={removed:false,setView(){return this},fitBounds(){return this},invalidateSize(){return this},remove(){this.removed=true}};maps.push(m);return m;},marker:()=>({addTo(){return this},bindPopup(){return this}}),polyline:()=>({addTo(){return this},bindPopup(){return this}}),tileLayer:()=>({on(){return this},addTo(){return this}})};
let calls=[],state='initial',deferred=null;
function result(k=key,cacheOnly=false){
 const empty=state==='empty'||(state==='initial'&&cacheOnly);
 return {ok:true,public_key:k,experimental:false,state:empty?'empty':state==='initial'?'available':state,
 error:state==='blocked'?'External monitoring unavailable: HTTP 403 / Cloudflare 1010':null,
 data:empty?null:data,fetched_at:empty?null:1000,stale:empty||state==='stale'||state==='blocked'};
}
w.fetch=async(url,options)=>{calls.push(url);if(deferred){const fn=deferred;deferred=null;return fn(url);}const k=new URL(url,'http://localhost').searchParams.get('public_key');return {ok:true,json:async()=>result(k,url.includes('cache_only=1'))};};
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));};
const toggle=(id,open)=>{$(id).open=open;$(id).dispatchEvent(new w.Event('toggle'));};
const select=k=>{w.meshcorestationSelectedRepeater=k;w.document.dispatchEvent(new w.CustomEvent('managed-repeater-selected',{detail:k}));};
(async()=>{
 w.eval(fs.readFileSync('meshcorestation/web/assets/aa_display.js','utf8'));
 w.eval(fs.readFileSync('meshcorestation/web/assets/ab_repeater_names.js','utf8'));
 w.eval(fs.readFileSync('meshcorestation/web/assets/ac_network_relationships.js','utf8'));
 w.eval(fs.readFileSync('meshcorestation/web/assets/network_monitoring.js','utf8'));await settle();assert.equal(calls.length,0);
 toggle('repeater-optimizer-disclosure',true);await settle();assert.equal(calls.length,0);
 toggle('repeater-network-disclosure',true);await settle();assert(calls[0].includes('cache_only=1'));assert(calls.some(x=>!x.includes('cache_only=1')),'stale data automatically fetched with no activation flag');assert($('network-content').textContent.includes('107'));
 assert(!/experimental|live integration unverified/i.test($('network-status').textContent));
 state='available';toggle('repeater-network-disclosure',false);await settle();const fresh=calls.length;toggle('repeater-network-disclosure',true);await settle();assert(calls.slice(fresh).every(x=>x.includes('cache_only=1')),'fresh cache reused');
 state='stale';$('network-refresh').click();await settle();assert(calls.at(-1).includes('refresh=1'));
 assert($('network-content').textContent.includes('107'));assert($('network-content').textContent.includes('inferred-only'));assert($('network-content').textContent.includes('Hemsbergturm'));assert($('network-content').textContent.includes('24.10.2026'));assert(!$('network-content').textContent.includes(key));assert($('network-content').querySelector('[title="'+key+'"]'));
 assert($('network-content').textContent.includes('Unknown'));assert($('network-status').textContent.includes('Stale'));assert(maps.length);
 state='blocked';$('network-refresh').click();await settle();assert($('network-status').textContent.includes('403'));assert($('network-content').textContent.includes('107'));
 assert($('network-content').querySelector('.stats-section .stats-table-scroll'));assert($('network-content').querySelector('.stats-metric'));
 assert.equal(maps.filter(m=>!m.removed).length,1,'only one active map after redraws');
 let resolve;deferred=url=>new Promise(r=>{resolve=()=>r({ok:true,json:async()=>result(key)})});
 $('network-refresh').click();await settle();assert(resolve);
 state='empty';select(other);await settle();assert.equal($('network-content').textContent,'');resolve();await settle();assert.equal($('network-content').textContent,'','old key never renders under new key');
 toggle('repeater-optimizer-disclosure',false);await settle();const count=calls.length;select(key);await settle();assert.equal(calls.length,count,'no selection request under closed parent');
 toggle('repeater-network-disclosure',false);toggle('repeater-optimizer-disclosure',true);await settle();assert.equal(calls.length,count);
 dom.window.close();console.log('Network monitoring fixtures, activation-free/blocked/stale states, maps, on-demand loading and stale-response isolation passed.');
})().catch(e=>{console.error(e);process.exit(1)});
