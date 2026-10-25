/* Two focused real-browser cases; no unrelated dashboard matrix or live API. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const key='769b90b4dd327d7bc9cc651fb8d2f8a4a217957cd36feac6b3216b5acedc36ff',other='ab'.repeat(32),output=process.env.BROWSER_OUTPUT||'browser-results';fs.mkdirSync(output,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true});let page;
try{for(const [width,height,colorScheme] of [[1280,960,'light'],[390,844,'dark']]){
 page=await browser.newPage({viewport:{width,height},colorScheme});
 await page.addInitScript(()=>{
   let loader;
   Object.defineProperty(window,'meshcorestationLoadMapLibrary',{configurable:true,get:()=>loader,set(fn){loader=async(...args)=>{const result=await fn(...args);if(!L.__neighborTestWrapped){const original=L.map;L.map=function(...args){const m=original.apply(this,args);if(args[0]?.classList?.contains('performance-neighbor-canvas')){window.__neighborMap=m;window.__neighborEvents=[];m.on('dragstart drag dragend moveend',e=>window.__neighborEvents.push(e.type));m.getContainer().addEventListener('mousedown',e=>window.__neighborDown={which:e.which,button:e.button,target:e.target.tagName},true);}return m;};L.__neighborTestWrapped=true;}return result;};}});
 });const requests=[],errors=[];page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await page.goto('http://127.0.0.1:8050');await page.locator('#repeater-management-disclosure > summary').click();await page.waitForFunction(k=>document.querySelector('#managed-repeater')?.value===k,key);
 await page.locator('#repeater-optimizer-disclosure > summary').click();const initialResponse=page.waitForResponse(r=>r.url().includes('/api/repeater-performance')&&r.request().method()==='GET');await page.locator('#repeater-performance-disclosure > summary').click();const initial=await (await initialResponse).json();
 const map=page.locator('#performance-neighbor-map');await map.locator('.leaflet-marker-icon').first().waitFor();
 const order=await page.locator('#performance-content').evaluate(n=>[...n.children].map(n=>n.id));assert.equal(order[order.indexOf('performance-connectivity')+1],'performance-neighbor-map');assert.equal(order[order.indexOf('performance-neighbor-map')+1],'performance-routing');
 assert.equal(await page.locator('#performance-content svg.performance-chart').count(),4);assert(await page.locator('#performance-assessment').isVisible());assert.equal(await page.locator('#performance-contribution .stats-metric').count(),4);
 assert.deepEqual(await map.locator('.stats-metric strong').allTextContents(),['14','4','10','0']);
 const low=page.locator('#performance-neighbor-low');assert.equal(await low.isChecked(),false);
 const lines=()=>map.locator('path.network-relationship');assert.equal(await lines().count(),10);assert.equal(await map.locator('.neighbor-direction-bidirectional').count(),4);assert.equal(await map.locator('.neighbor-direction-unidirectional').count(),6);
 const colors=await lines().evaluateAll(nodes=>nodes.map(n=>({color:getComputedStyle(n).stroke,length:n.getTotalLength(),d:n.getAttribute('d')})));assert(colors.every(n=>n.length>1&&n.color!=='none'));assert.equal(new Set(colors.map(n=>n.color)).size,2);
 assert.equal(await map.locator('.leaflet-marker-icon').count(),11);assert.equal(await map.locator('.leaflet-marker-icon img').count(),0,'markers have no image dependencies');assert.equal(await map.locator('.performance-neighbor-selected').evaluate(n=>getComputedStyle(n).backgroundColor),'rgb(36, 105, 216)');
 assert((await map.locator('.performance-neighbor-missing').innerText()).includes('Pagan REP'));assert(!(await map.locator('.performance-neighbor-missing').innerText()).includes('Muletto3 Repeater Prova'));
 assert((await map.innerText()).includes('24-hour observation window'));
 const beforeFilter=requests.filter(u=>u.includes('/api/repeater-performance')||u.includes('/api/repeater-network')).length;await low.check();assert.equal(await map.locator('.leaflet-marker-icon').count(),13);assert((await map.locator('.performance-neighbor-missing').innerText()).includes('Muletto3 Repeater Prova'));assert.equal(await lines().count(),12);assert.equal(await map.locator('.neighbor-confidence-low').count(),2);assert(await map.locator('.neighbor-confidence-low').evaluateAll(ns=>ns.every(n=>getComputedStyle(n).strokeDasharray!=='none')));await low.uncheck();assert.equal(await lines().count(),10);assert.equal(await map.locator('.leaflet-marker-icon').count(),11);assert.equal(requests.filter(u=>u.includes('/api/repeater-performance')||u.includes('/api/repeater-network')).length,beforeFilter,'filtering is local, with no new Analyzer request');
 await map.screenshot({path:`${output}/neighbor-map-${width}-${colorScheme}.png`});
 const selected=map.locator('.performance-neighbor-selected');await selected.scrollIntoViewIfNeeded();const box=await selected.boundingBox(),oldPath=await lines().first().getAttribute('d');await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.wheel(0,-750);
 await page.waitForFunction(old=>document.querySelector('#performance-neighbor-map path.network-relationship')?.getAttribute('d')!==old,oldPath);
 await map.locator('.leaflet-marker-icon[title="🐝Heppenheim Nord"]').click();
 const popup=map.locator('.leaflet-popup-content');await popup.waitFor();const text=await popup.innerText();for(const word of ['🐝Heppenheim Nord','1.5 km',String(initial.neighbor_map.neighbors[0].weHear),'391','high','inferred'])assert(text.includes(word),word);await map.screenshot({path:`${output}/neighbor-popup-${width}-${colorScheme}.png`});await map.locator('.leaflet-popup-close-button').click();
 // Resize and reopen retain one map with visible vector overlays, even without tiles.
 await page.setViewportSize({width:width===390?430:1100,height});await page.waitForFunction(()=>document.querySelectorAll('#performance-neighbor-map .leaflet-container').length===1);assert(await lines().count()>0);
 await page.waitForFunction(()=>!document.querySelector('#performance-neighbor-map .leaflet-zoom-anim'));
 const canvas=map.locator('.leaflet-container');await canvas.evaluate(n=>n.scrollIntoView({block:'center',inline:'nearest'}));
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const point=await canvas.evaluate(n=>{
   const r=n.getBoundingClientRect(),free=(x,y)=>{const e=document.elementFromPoint(x,y);return e?.closest('.leaflet-container')===n&&!e.closest('.leaflet-popup,.leaflet-control,.leaflet-marker-icon');};
   for(const xf of [.1,.25,.5,.7])for(const yf of [.2,.4,.6,.8]){const x=r.x+r.width*xf,y=r.y+r.height*yf;if(free(x,y)&&free(x+45,y+25))return {x,y};}
   throw Error('No clear map background available for drag input');
 });
 const position=()=>page.evaluate(()=>{const c=window.__neighborMap.getCenter();return {lat:c.lat,lng:c.lng};});
 const beforePan=await position(),beforeDrags=await page.evaluate(()=>window.__neighborEvents.filter(e=>e==='dragstart').length);
 await page.mouse.move(point.x,point.y);await page.mouse.down();await page.mouse.move(point.x+45,point.y+25,{steps:8});await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));await page.mouse.up();

 const afterPan=await position();
 if(afterPan.lat===beforePan.lat&&afterPan.lng===beforePan.lng)console.log('Pan diagnostics',await page.evaluate(()=>({events:window.__neighborEvents,down:window.__neighborDown,enabled:window.__neighborMap.dragging.enabled(),globalDragging:!!L.Draggable._dragging,pane:window.__neighborMap._mapPane.className})));
 assert(await page.evaluate(old=>window.__neighborEvents.filter(e=>e==='dragstart').length>old,beforeDrags),'native Leaflet drag event');
 assert.notDeepEqual(afterPan,beforePan,'native mouse dragging changes the map center');


 const reopened=page.waitForResponse(r=>r.url().includes('/api/repeater-performance')&&new URL(r.url()).searchParams.get('public_key')===key&&!new URL(r.url()).searchParams.has('refresh'));await page.locator('#repeater-performance-disclosure > summary').click();await page.locator('#repeater-performance-disclosure > summary').click();await reopened;await page.waitForFunction(()=>document.querySelector('#performance-content')?.getAttribute('aria-busy')==='false');await map.locator('.leaflet-marker-icon').first().waitFor();assert.equal(await map.locator('.leaflet-container').count(),1);
 // Hold one refresh at the request boundary to verify progress deterministically.
 let releaseRefresh,markHeld;const heldReady=new Promise(resolve=>markHeld=resolve);const held=async route=>{if(new URL(route.request().url()).searchParams.get('refresh')==='1')await new Promise(resolve=>{releaseRefresh=resolve;markHeld();});await route.continue();};
 await page.route('**/api/repeater-performance?*',held);
 const refreshedResponse=page.waitForResponse(r=>r.url().includes('/api/repeater-performance')&&new URL(r.url()).searchParams.get('refresh')==='1');
 await page.locator('#performance-refresh').click();await heldReady;await page.getByText('Refreshing Analyzer measurements… Saved observations remain visible.',{exact:true}).waitFor();assert(await page.locator('#performance-refresh').isDisabled());
 assert.equal(await page.locator('[data-metric="Relay Activity"] strong').innerText(),String(initial.dashboard.cards.relay_24h));
 await page.waitForFunction(()=>document.querySelector('#performance-refresh').disabled);assert(releaseRefresh);releaseRefresh();const refreshed=await (await refreshedResponse).json();
 await page.waitForFunction(()=>document.querySelector('#performance-content')?.getAttribute('aria-busy')==='false');await map.locator('.leaflet-marker-icon').first().waitFor();
 assert.equal(refreshed.analyzer_refresh.state,'available');assert.equal(await page.locator('[data-metric="Relay Activity"] strong').innerText(),String(initial.dashboard.cards.relay_24h+1));assert(refreshed.neighbor_map.fetched_at>initial.neighbor_map.fetched_at);
 assert(refreshed.dashboard.forwarding.some(r=>r.hourly_relays===77));assert(await page.locator('#performance-forwarding circle[data-value="77"]').count()>0);assert.equal(refreshed.neighbor_map.neighbors[0].weHear,initial.neighbor_map.neighbors[0].weHear+1);assert.equal(await map.locator('.leaflet-marker-icon').count(),11);
 assert((await page.locator('#performance-status').innerText()).includes('Analyzer refreshed'));assert(!await page.locator('#performance-refresh').isDisabled());
 await page.unroute('**/api/repeater-performance?*',held);
 await page.evaluate(k=>window.__neighborMap.eachLayer(layer=>{if(layer.options?.neighborKey===k&&layer.openPopup)layer.openPopup();}),refreshed.neighbor_map.neighbors[0].pubkey);await map.locator('.leaflet-popup-content').waitFor();assert((await map.locator('.leaflet-popup-content').innerText()).includes(String(refreshed.neighbor_map.neighbors[0].weHear)),'refreshed map popup uses new directional observations');
 const failed={...refreshed,analyzer_refresh:{state:'blocked',error:'Analyzer HTTP 403; provider access denied.'}};
 const denied=route=>new URL(route.request().url()).searchParams.get('refresh')==='1'?route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(failed)}):route.continue();
 await page.route('**/api/repeater-performance?*',denied);await page.locator('#performance-refresh').click();await page.getByText('Analyzer refresh failed:',{exact:false}).waitFor();assert((await page.locator('#performance-status').innerText()).includes('retained'));assert.equal(await page.locator('[data-metric="Relay Activity"] strong').innerText(),String(refreshed.dashboard.cards.relay_24h));await page.unroute('**/api/repeater-performance?*',denied);
 const response=page.waitForResponse(r=>r.url().includes('/api/repeater-performance')&&r.url().includes(other));await page.locator('#managed-repeater').selectOption(other);await response;await page.waitForFunction(()=>document.querySelector('#performance-content')?.getAttribute('aria-busy')==='false');assert.equal(await map.locator('.leaflet-marker-icon').count(),0);assert((await map.innerText()).includes('No saved Analyzer relationship snapshot'));
 assert.equal(requests.filter(u=>u.includes('/api/repeater-network')||u.includes('analyzer.meshcorenetz')).length,0,'map never fetches Analyzer');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);await page.close();
}console.log('Neighbor map Chromium: desktop light/mobile dark, real markers and green/red SVG lines, low-confidence toggle, popup values, zoom, resize/reopen, missing coordinates, repeater switch manual Analyzer refresh/progress/error retention and local-only filtering passed.');
}catch(e){if(page&&!page.isClosed())await page.screenshot({path:output+'/neighbor-map-failure.png'});throw e;}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
