/* Two focused real-browser cases; no unrelated dashboard matrix or live API. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const key='769b90b4dd327d7bc9cc651fb8d2f8a4a217957cd36feac6b3216b5acedc36ff',other='ab'.repeat(32),output=process.env.BROWSER_OUTPUT||'browser-results';fs.mkdirSync(output,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true});let page;
try{for(const [width,height,colorScheme] of [[1280,960,'light'],[390,844,'dark']]){
 page=await browser.newPage({viewport:{width,height},colorScheme});const requests=[],errors=[];page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await page.goto('http://127.0.0.1:8050');await page.locator('#repeater-management-disclosure > summary').click();await page.waitForFunction(k=>document.querySelector('#managed-repeater')?.value===k,key);
 await page.locator('#repeater-optimizer-disclosure > summary').click();await page.locator('#repeater-performance-disclosure > summary').click();
 const map=page.locator('#performance-neighbor-map');await map.locator('.leaflet-marker-icon').first().waitFor();
 const order=await page.locator('#performance-content').evaluate(n=>[...n.children].map(n=>n.id));assert.equal(order[order.indexOf('performance-connectivity')+1],'performance-neighbor-map');assert.equal(order[order.indexOf('performance-neighbor-map')+1],'performance-routing');
 assert.equal(await page.locator('#performance-content svg.performance-chart').count(),4);assert(await page.locator('#performance-assessment').isVisible());assert.equal(await page.locator('#performance-contribution .stats-metric').count(),4);
 assert.deepEqual(await map.locator('.stats-metric strong').allTextContents(),['14','4','10','0']);
 const low=page.locator('#performance-neighbor-low');assert.equal(await low.isChecked(),false);
 const lines=()=>map.locator('path.network-relationship');assert.equal(await lines().count(),10);assert.equal(await map.locator('.neighbor-direction-bidirectional').count(),4);assert.equal(await map.locator('.neighbor-direction-unidirectional').count(),6);
 const colors=await lines().evaluateAll(nodes=>nodes.map(n=>({color:getComputedStyle(n).stroke,length:n.getTotalLength(),d:n.getAttribute('d')})));assert(colors.every(n=>n.length>1&&n.color!=='none'));assert.equal(new Set(colors.map(n=>n.color)).size,2);
 assert.equal(await map.locator('.leaflet-marker-icon').count(),13);assert.equal(await map.locator('.leaflet-marker-icon img').count(),0,'markers have no image dependencies');assert.equal(await map.locator('.performance-neighbor-selected').evaluate(n=>getComputedStyle(n).backgroundColor),'rgb(36, 105, 216)');
 assert((await map.locator('.performance-neighbor-missing').innerText()).includes('Pagan REP'));assert((await map.locator('.performance-neighbor-missing').innerText()).includes('Muletto3 Repeater Prova'));
 assert((await map.innerText()).includes('24-hour observation window'));
 await low.check();assert.equal(await lines().count(),12);assert.equal(await map.locator('.neighbor-confidence-low').count(),2);assert(await map.locator('.neighbor-confidence-low').evaluateAll(ns=>ns.every(n=>getComputedStyle(n).strokeDasharray!=='none')));await low.uncheck();assert.equal(await lines().count(),10);
 await map.screenshot({path:`${output}/neighbor-map-${width}-${colorScheme}.png`});
 const selected=map.locator('.performance-neighbor-selected');await selected.scrollIntoViewIfNeeded();const box=await selected.boundingBox(),oldPath=await lines().first().getAttribute('d');await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.wheel(0,-750);
 await page.waitForFunction(old=>document.querySelector('#performance-neighbor-map path.network-relationship')?.getAttribute('d')!==old,oldPath);
 await map.locator('.leaflet-marker-icon[title="🐝Heppenheim Nord"]').click();
 const popup=map.locator('.leaflet-popup-content');await popup.waitFor();const text=await popup.innerText();for(const word of ['🐝Heppenheim Nord','1.5 km','148','391','high','inferred'])assert(text.includes(word),word);await map.screenshot({path:`${output}/neighbor-popup-${width}-${colorScheme}.png`});await map.locator('.leaflet-popup-close-button').click();
 // Resize and reopen retain one map with visible vector overlays, even without tiles.
 await page.setViewportSize({width:width===390?430:1100,height});await page.waitForFunction(()=>document.querySelectorAll('#performance-neighbor-map .leaflet-container').length===1);assert(await lines().count()>0);
 const canvas=map.locator('.leaflet-container');await canvas.scrollIntoViewIfNeeded();
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const bounds=await canvas.boundingBox();
 const position=()=>map.evaluate(n=>JSON.stringify([...n.querySelectorAll('.leaflet-map-pane,.leaflet-marker-icon,path.network-relationship')].map(e=>[e.getAttribute('style'),e.getAttribute('d')])));
 const beforePan=await position();await page.mouse.move(bounds.x+bounds.width*.25,bounds.y+bounds.height*.6);await page.mouse.down();await page.mouse.move(bounds.x+bounds.width*.25+60,bounds.y+bounds.height*.6+35,{steps:8});await page.mouse.up();
 await page.waitForFunction(old=>JSON.stringify([...document.querySelectorAll('#performance-neighbor-map .leaflet-map-pane,#performance-neighbor-map .leaflet-marker-icon,#performance-neighbor-map path.network-relationship')].map(e=>[e.getAttribute('style'),e.getAttribute('d')]))!==old,beforePan);

 await page.locator('#repeater-performance-disclosure > summary').click();await page.locator('#repeater-performance-disclosure > summary').click();await map.locator('.leaflet-marker-icon').first().waitFor();assert.equal(await map.locator('.leaflet-container').count(),1);
 const response=page.waitForResponse(r=>r.url().includes('/api/repeater-performance')&&r.url().includes(other));await page.locator('#managed-repeater').selectOption(other);await response;await page.waitForFunction(()=>document.querySelector('#performance-content')?.getAttribute('aria-busy')==='false');assert.equal(await map.locator('.leaflet-marker-icon').count(),0);assert((await map.innerText()).includes('No saved Analyzer relationship snapshot'));
 assert.equal(requests.filter(u=>u.includes('/api/repeater-network')||u.includes('analyzer.meshcorenetz')).length,0,'map never fetches Analyzer');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);await page.close();
}console.log('Neighbor map Chromium: desktop light/mobile dark, real markers and green/red SVG lines, low-confidence toggle, popup values, zoom, resize/reopen, missing coordinates, repeater switch and cache-only behavior passed.');
}catch(e){if(page&&!page.isClosed())await page.screenshot({path:output+'/neighbor-map-failure.png'});throw e;}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
