/* Exercise the real loader + Leaflet + cluster plugin, including cold starts. */
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=name=>fs.readFileSync('meshcorestation/web/assets/'+name,'utf8');
const pause=()=>new Promise(resolve=>setImmediate(resolve));
async function until(check,label){for(let i=0;i<500;i++){if(check())return;await new Promise(resolve=>setTimeout(resolve,5));}throw Error('Timed out: '+label);}
function environment(count,{width=1024,failAsset='',api='',renderFailure='',stalledAsset='',timeoutAPI=false}={}){
 const dom=new JSDOM('<button id="open-repeaters">Open map</button><dialog id="repeaters-dialog"><button id="close-repeaters">Close</button><div id="repeater-map"></div><div id="repeater-notes"></div></dialog>',{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window,d=w.document;
 const canvas=d.getElementById('repeater-map'),dialog=d.getElementById('repeaters-dialog'),notes=d.getElementById('repeater-notes');
 Object.defineProperty(canvas,'clientWidth',{value:width});Object.defineProperty(canvas,'clientHeight',{value:width<700?420:600});
 dialog.showModal=()=>dialog.setAttribute('open','');dialog.close=()=>{dialog.removeAttribute('open');dialog.dispatchEvent(new w.Event('close'));};
 w.matchMedia=()=>({matches:true});w.requestAnimationFrame=fn=>{fn();return 1};
 w.meshcorestationFormatDate=()=> 'saved time';
 w.meshcorestationRepeaterActions=(box,node)=>{const button=d.createElement('button');button.textContent='Manage '+node.label;box.append(button);};
 const timers=w.setTimeout.bind(w);
 w.setTimeout=(fn,delay,...args)=>timers(fn,(stalledAsset&&delay===15000)||(timeoutAPI&&delay===30000)?10:delay,...args);
 const nodes=Array.from({length:count},(_,i)=>({role:'repeater',public_key:i.toString(16).padStart(64,'0'),label:'Repeater '+i,position:[48+(i%73)*.05,8+Math.floor(i/73)*.05],updated_at:123}));
 nodes.push({role:'bot',label:'Station',position:[50,9]});
 const payload={nodes,segments:[],notes:[`${count} repeaters have usable coordinates.`],hops:[]};
 let currentAPI=api,fail=failAsset,stall=stalledAsset,renderFail=renderFailure;
 const calls={assets:[],maps:[],groups:[],tiles:[],batches:[],loading:[],fetch:0,resize:[],observers:[]};
 let onFetch;
 w.fetch=async(url,{signal})=>{
  calls.fetch++;
  if(onFetch)onFetch();
  if(timeoutAPI)return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new w.DOMException('Aborted','AbortError')),{once:true}));
  if(currentAPI==='network')throw TypeError('Network request failed');
  if(currentAPI==='invalid')return {ok:true,json:async()=>{throw Error('JSON');}};
  if(currentAPI==='shape')return {ok:true,json:async()=>({})};
  if(currentAPI==='503')return {ok:false,status:503,json:async()=>({error:'Map database unavailable'})};
  return {ok:true,json:async()=>payload};
 };
 w.ResizeObserver=class{constructor(callback){this.callback=callback;calls.observers.push(this)}observe(){}disconnect(){this.disconnected=true}};
 const append=d.head.append.bind(d.head);
 d.head.append=element=>{
  const url=new URL(element.src||element.href).pathname;calls.assets.push(url);append(element);
  if(url===stall)return;
  setImmediate(()=>{
   if(url===fail){element.dispatchEvent(new w.Event('error'));return;}
   if(element.tagName==='SCRIPT'){
    w.eval(source(url.replace('/assets/','')));
    if(url.endsWith('/leaflet.js')){
     w.L.Browser.svg=true;
     const map=w.L.map;
     w.L.map=(...args)=>{
      if(renderFail==='initialize')throw 'Map initialization rejected';
      const instance=map(...args);calls.maps.push(instance);
      const invalidate=instance.invalidateSize;
      instance.invalidateSize=function(...args){calls.resize.push(args);if(renderFail==='frame')throw 'Map layout failed';return invalidate.apply(this,args)};
      return instance;
     };
     w.L.tileLayer=()=>{
      if(renderFail==='tiles')throw 'Tile initialization failed';
      const tile={on(event,handler){this[event]=handler;return this},addTo(){calls.tiles.push(this);return this}};return tile;
     };
    }else{
     const cluster=w.L.markerClusterGroup;
     w.L.markerClusterGroup=(...args)=>{
      if(renderFail==='cluster')throw 'Cluster initialization failed';
      const group=cluster(...args);calls.groups.push(group);
      const add=group.addLayers;
      group.addLayers=function(markers){
       calls.batches.push(markers.length);calls.loading.push(notes.querySelector('.map-loading')?.textContent);
       return add.call(this,markers);
      };return group;
     };
    }
   }
   element.dispatchEvent(new w.Event('load'));
  });
 };
 for(const name of ['aa_map_loader.js','aa_marker_clusters.js','maps.js'])w.eval(source(name));
 return {w,d,dom,canvas,dialog,notes,calls,payload,open(){d.getElementById('open-repeaters').click()},close(){dialog.close()},setAPI(value){currentAPI=value},setFailure(value){fail=value;stall='';renderFail=''},onFetch(callback){onFetch=callback}};
}
(async()=>{
 for(const [count,width] of [[700,1024],[703,390],[1000,390],[2000,1024]]){
  const e=environment(count,{width});e.open();
  assert(e.notes.textContent.includes('Loading map'));
  await until(()=>e.notes.querySelector('.map-ready')||e.notes.querySelector('.map-error'),'large map ready');
  assert(!e.notes.querySelector('.map-error'),e.notes.textContent);
  assert.equal(e.canvas.getAttribute('aria-busy'),'false');
  assert.equal(e.calls.maps.length,1);assert.equal(e.calls.maps[0].getMaxZoom(),19);
  assert.equal(e.calls.groups[0].getLayers().length,count);
  assert(e.calls.batches.length>=Math.ceil(count/100));assert(e.calls.batches.every(n=>n<=100));
  assert(e.calls.loading.every(Boolean),'Loading status must remain through every batch');
  assert.equal(e.calls.tiles.length,1);assert(e.canvas.querySelector('.leaflet-map-pane'));
  assert(e.canvas.querySelector('.repeater-cluster'),'Cluster badges must render');
  assert.equal(new Set(e.calls.assets).size,4,'Core and clustering JS/CSS must each load once');
  const map=e.calls.maps[0],group=e.calls.groups[0],marker=group.getLayers()[0];
  assert.equal(marker.getPopup().getContent()().querySelector('strong').textContent,'Repeater 0');
  assert(marker.getPopup().getContent()().querySelector('button').textContent.includes('Manage Repeater 0'));
  const initiallyVisible=group.getVisibleParent(marker);assert(initiallyVisible instanceof e.w.L.MarkerCluster);
  map.setView(marker.getLatLng(),19);assert(group.getVisibleParent(marker)===marker,'Zoom must separate repeaters');
  e.calls.tiles[0].tileerror();assert(e.notes.textContent.includes('Background tiles unavailable'));assert(map.hasLayer(group));
  const resize=e.calls.resize.length;e.calls.observers[0].callback();assert.equal(e.calls.resize.length,resize+1);
  e.close();assert(e.calls.observers[0].disconnected);assert.equal(Object.keys(map._layers).length,0);
  e.open();await until(()=>e.notes.querySelector('.map-ready'),'reopen');assert.equal(e.calls.fetch,1,'Keep recent route/map caching');
  e.close();e.dom.window.close();
 }
 for(const asset of ['/assets/vendor/leaflet.js','/assets/vendor/leaflet.css','/assets/vendor/leaflet.markercluster.js','/assets/vendor/MarkerCluster.css']){
  const e=environment(703,{failAsset:asset});e.open();await until(()=>e.notes.querySelector('.map-error'),'asset error');
  assert(e.notes.textContent.includes(asset));assert(e.notes.querySelector('[role="alert"]'));assert(!e.notes.querySelector('.map-loading'));
  e.setFailure('');e.notes.querySelector('button').click();await until(()=>e.notes.querySelector('.map-ready'),'asset retry');
  assert.equal(e.calls.groups.at(-1).getLayers().length,703);e.close();e.dom.window.close();
 }
 for(const api of ['network','invalid','shape','503']){
  const e=environment(700,{api});e.open();await until(()=>e.notes.querySelector('.map-error'),'API error');
  assert(e.notes.querySelector('.map-error').textContent.length>10);assert.equal(e.canvas.getAttribute('aria-busy'),'false');
  e.setAPI('');e.notes.querySelector('button').click();await until(()=>e.notes.querySelector('.map-ready'),'API retry');e.close();e.dom.window.close();
 }
 for(const renderFailure of ['initialize','cluster','frame','tiles']){
  const e=environment(700,{renderFailure});e.open();await until(()=>e.notes.querySelector('.map-error'),'render failure');
  assert(e.notes.querySelector('.map-error').textContent.includes('failed')||e.notes.querySelector('.map-error').textContent.includes('rejected'));
  assert.equal(e.canvas.getAttribute('aria-busy'),'false');e.close();e.dom.window.close();
 }
 const stalled=environment(700,{stalledAsset:'/assets/vendor/leaflet.css'});stalled.open();await until(()=>stalled.notes.querySelector('.map-error'),'stalled CSS');assert(stalled.notes.textContent.includes('Timed out'));stalled.close();stalled.dom.window.close();
 const timeout=environment(700,{timeoutAPI:true});timeout.open();await until(()=>timeout.notes.querySelector('.map-error'),'stalled API');assert(timeout.notes.textContent.includes('timed out'));timeout.close();timeout.dom.window.close();
 // Closing during a chunk must stop work; reopening must not receive stale work.
 const cancelled=environment(2000);cancelled.open();await until(()=>cancelled.calls.batches.length>0,'first chunk');cancelled.close();const done=cancelled.calls.batches.length;
 await new Promise(resolve=>setTimeout(resolve,20));assert.equal(cancelled.calls.batches.length,done);
 cancelled.open();await until(()=>cancelled.notes.querySelector('.map-ready'),'reopen cancelled map');assert.equal(cancelled.calls.groups.at(-1).getLayers().length,2000);cancelled.close();cancelled.dom.window.close();
 console.log('Known maps: 700/703/1000/2000 markers, mobile sizing, clustering/popups, chunk loading, cold assets/retries, API/render/tile failures, timeouts, resize and cancellation passed.');
})().catch(error=>{console.error(error);process.exit(1)});
