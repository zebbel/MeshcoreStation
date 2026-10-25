const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const source='meshcorestation/web/assets/',root='tests/fixtures/analyzer/responses/',detail=JSON.parse(fs.readFileSync(root+'node_detail_24h.json')),reach=JSON.parse(fs.readFileSync(root+'node_reach_1d.json')),key=detail.node.id;
const dom=new JSDOM('<body></body>',{runScripts:'outside-only',url:'http://localhost'}),w=dom.window;w.meshcorestationFormatDate=String;w.fetch=()=>{throw Error('No Analyzer requests')};w.setInterval=()=>{throw Error('No polling')};w.requestAnimationFrame=fn=>w.setTimeout(fn,0);w.cancelAnimationFrame=w.clearTimeout;
for(const file of ['ab_repeater_names.js','ac_network_relationships.js','ad_neighbor_communication_map.js'])w.eval(fs.readFileSync(source+file,'utf8'));
let created=0,removed=0,points=[],lines=[],map;const layer=options=>({options,addTo(m){m.layers.push(this);return this;},bindPopup(fn){this.popup=fn;return this;}});
w.L={map(){created++;map={layers:[],setView(){return this;},fitBounds(){},invalidateSize(){},removeLayer(l){this.layers=this.layers.filter(x=>x!==l);},eachLayer(fn){this.layers.forEach(fn);},remove(){removed++;}};return map;},divIcon:o=>o,marker:(pos,opts)=>{const l=layer(opts);points.push(l);return l;},polyline:(pos,opts)=>{const l=layer(opts);lines.push(l);return l;},tileLayer:()=>({...layer({}),on(){return this;}})};
w.meshcorestationLoadMapLibrary=async()=>{};
const settle=async()=>{for(let i=0;i<4;i++)await new Promise(r=>setImmediate(r));};
(async()=>{
 const api=w.MeshcoreStationNeighborMap,rows=api.neighbors(reach.neighbourList,key),counts=api.summary(rows);
 assert.equal(counts.total,14);assert.equal(counts.bidirectional,4);assert.equal(counts.unidirectional,10);assert.equal(counts.unknown,0);
 const unknown={...rows[0],pubkey:'ff'.repeat(32),weHear:1,theyHear:null,twoWay:false};assert.equal(api.summary([unknown]).unknown,1,'positive count without reciprocal evidence is unknown, not one-way');
 const conflict=api.neighbors([rows[0],{...rows[0],theyHear:0}],key);assert.equal(conflict.length,1);assert.equal(api.summary(conflict).unknown,1);
 const view=api.create({available:true,fetched_at:Date.now()/1000,center:detail.node,neighbors:reach.neighbourList},key,()=>true);w.document.body.append(view.element);await settle();
 assert.equal(created,1);assert.equal(points.length,13); // selected + 12 located repeater neighbors
 assert(points[0].options.icon.html.classList.contains('performance-neighbor-selected'));
 assert.equal(view.element.querySelector('input').checked,false);
 const actual=()=>map.layers.filter(l=>l.options.className?.includes('neighbor-direction-'));
 assert.equal(actual().length,10);assert.equal(actual().filter(l=>l.options.color==='var(--green)').length,4);assert.equal(actual().filter(l=>l.options.color==='var(--red)').length,6);
 const text=points[1].popup().textContent;assert(text.includes('🐝Heppenheim Nord')&&text.includes('1.5 km')&&text.includes('148')&&text.includes('391')&&text.includes('high'));
 assert(view.element.querySelector('.performance-neighbor-missing').textContent.includes('Pagan REP'));assert(view.element.querySelector('.performance-neighbor-missing').textContent.includes('Muletto3 Repeater Prova'));
 const check=view.element.querySelector('input');check.checked=true;check.dispatchEvent(new w.Event('change'));assert.equal(actual().length,12);assert.equal(actual().filter(l=>l.options.dashArray==='8 7').length,2);assert.equal(points.length,13,'filter does not duplicate markers');
 check.checked=false;check.dispatchEvent(new w.Event('change'));assert.equal(actual().length,10);view.dispose();assert.equal(removed,1);
 let finish;w.meshcorestationLoadMapLibrary=()=>new Promise(r=>finish=r);
 const stale=api.create({available:true,center:detail.node,neighbors:[]},key,()=>true);w.document.body.append(stale.element);await settle();stale.dispose();finish();await settle();assert.equal(created,1,'outdated pending maps never initialize');
 dom.window.close();console.log('Neighbor map: observed directional counts, unknown/conflicting evidence, blue selected marker, green/red links, low-confidence toggle, marker details, missing coordinates and disposal passed.');
})().catch(e=>{console.error(e);process.exit(1)});
