/* Real local API/database CRUD and rendered performance charts in Chromium. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const key='769b90b4dd327d7bc9cc651fb8d2f8a4a217957cd36feac6b3216b5acedc36ff',other='ab'.repeat(32),output=process.env.BROWSER_OUTPUT||'browser-results';fs.mkdirSync(output,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true});let active;
try{for(const viewport of [{width:1280,height:960},{width:390,height:844}])for(const colorScheme of ['light','dark']){
 const page=await browser.newPage({viewport,colorScheme}),token=viewport.width+'-'+colorScheme,requests=[],errors=[];active=page;
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto('http://127.0.0.1:8050');
 await page.locator('#repeater-management-disclosure > summary').click();await page.waitForFunction(k=>document.querySelector('#managed-repeater')?.value===k,key);
 assert.equal(requests.filter(r=>r.url.includes('/api/repeater-performance')).length,0,'closed performance never loads');
 await page.locator('#repeater-optimizer-disclosure > summary').click();
 const order=await page.locator('#repeater-optimizer-disclosure > details').evaluateAll(nodes=>nodes.map(n=>n.id));assert.equal(order[0],'repeater-performance-disclosure');
 await page.locator('#repeater-performance-disclosure > summary').click();await page.getByText('Saved observations loaded.',{exact:false}).first().waitFor();
 assert.equal(await page.locator('#performance-selected').innerText(),'DE_HE_HP_RPT1');assert.equal(await page.locator('#performance-content .stats-metric').count(),4);
 const section=page.locator('#repeater-performance-disclosure');
 assert(await page.locator('.performance-overview').innerText().then(t=>t.includes('Performance Trend')&&t.includes('Data completeness')));
 assert.equal(await page.locator('#performance-history').getAttribute('open'),null);
 assert.equal(await page.locator('#performance-details').getAttribute('open'),null);
 await page.locator('#performance-history > summary').click();
 await page.locator('#performance-changes > summary').click();
 await page.locator('.performance-overview').screenshot({path:`${output}/performance-overview-${token}.png`});
 assert.equal(await section.locator('svg.performance-chart').count(),3);assert(await section.locator('.performance-change-line').count()>=3);
 assert(await section.locator('svg.performance-chart circle').count()>0);
 const reachTicks=await section.locator('svg.performance-chart').nth(2).locator('text[text-anchor="end"]').allTextContents();assert(reachTicks.filter(t=>/^\d/.test(t)).every(t=>!t.includes('.')),'neighbor axes use whole counts');
 const hourlyPaths=await section.locator('svg.performance-chart').nth(1).locator('path[stroke-width="2"]').getAttribute('d');assert((hourlyPaths.match(/M/g)||[]).length>=2,'missing hourly observations break the rendered line');
 const geometry=await section.locator('.performance-marker-line').evaluateAll(nodes=>nodes.map(n=>({length:n.getTotalLength(),width:n.getBBox().width,height:n.getBBox().height,stroke:getComputedStyle(n).stroke})));assert(geometry.every(n=>n.length>100&&n.height>100&&n.stroke!=='none'));
 assert((await section.innerText()).includes('Verified flood.max'));
 assert.equal(requests.filter(r=>r.url.includes('/api/repeater-network')).length,0,'performance does not fetch Analyzer data');
 await section.screenshot({path:`${output}/performance-${token}.png`});
 await section.locator('.performance-change-line').last().click();await page.locator('#performance-comparison').waitFor();
 assert((await page.locator('#performance-comparison').innerText()).includes('Correlation does not prove'));
 assert((await page.locator('#performance-comparison').innerText()).includes('overlap'));
 for(const days of ['1','3','7']){await Promise.all([page.waitForResponse(r=>r.url().includes('compare_days='+days)&&r.request().method()==='GET'),page.locator('#performance-comparison select').selectOption(days)]);}
 await page.locator('#performance-comparison').screenshot({path:`${output}/performance-comparison-${token}.png`});
 const comparisonTable=page.locator('#performance-comparison .stats-table-scroll');
 assert.equal(await comparisonTable.locator('td').nth(1).evaluate(n=>getComputedStyle(n).whiteSpace),'nowrap');
 if(viewport.width===390){assert(await comparisonTable.evaluate(n=>n.scrollWidth>n.clientWidth));await comparisonTable.evaluate(n=>{n.scrollLeft=n.scrollWidth;});await comparisonTable.screenshot({path:`${output}/performance-comparison-values-${token}.png`});await comparisonTable.evaluate(n=>{n.scrollLeft=0;});}

 for(const days of ['1','30','7']){const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/repeater-performance'&&new URL(r.url()).searchParams.get('days')===days);await page.locator('#performance-days').selectOption(days);await response;await page.getByText('Saved observations loaded.',{exact:false}).first().waitFor();}
 const description='Browser antenna test '+token;
 await page.locator('#performance-description').fill(description);
 let manualAt=null;
 if(viewport.width===390){const local=await page.evaluate(()=>{const d=new Date(Date.now()-86400000);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,19);});await page.locator('#performance-change-time').fill(local);manualAt=await page.evaluate(text=>new Date(text).getTime()/1000,local);}
 await page.getByRole('button',{name:'Save marker',exact:true}).click();
 let row=page.locator('#performance-content tr').filter({hasText:description});await row.waitFor();
 const saved=await page.request.get('http://127.0.0.1:8050/api/repeater-performance?public_key='+key,{headers:{'X-Meshcore-Control':'1'}}).then(r=>r.json());const marker=saved.markers.find(m=>m.description===description);assert(marker);if(manualAt!=null)assert.equal(marker.at,manualAt);
 await page.reload();await page.locator('#repeater-management-disclosure > summary').click();await page.waitForFunction(k=>document.querySelector('#managed-repeater')?.value===k,key);await page.locator('#repeater-optimizer-disclosure > summary').click();await page.locator('#repeater-performance-disclosure > summary').click();await page.locator('#performance-changes > summary').click();row=page.locator('#performance-content tr').filter({hasText:description});await row.waitFor();
 await row.getByRole('button',{name:'Edit',exact:true}).click();await page.locator('#performance-description').fill(description+' edited');await page.getByRole('button',{name:'Save marker',exact:true}).click();row=page.locator('#performance-content tr').filter({hasText:description+' edited'});await row.waitFor();
 const updated=await page.request.get('http://127.0.0.1:8050/api/repeater-performance?public_key='+key,{headers:{'X-Meshcore-Control':'1'}}).then(r=>r.json());assert.equal(updated.markers.find(m=>m.id===marker.id).at,marker.at,'editing text preserves the original timestamp');
 page.once('dialog',dialog=>dialog.accept());await row.getByRole('button',{name:'Delete',exact:true}).click();await row.waitFor({state:'detached'});
 const originalWidth=await section.locator('svg.performance-chart').first().getAttribute('viewBox');await page.setViewportSize({width:viewport.width===390?844:390,height:viewport.height});await page.waitForFunction(original=>document.querySelector('.performance-chart')?.getAttribute('viewBox')!==original,originalWidth);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no page overflow');
 await page.locator('#managed-repeater').selectOption(other);await page.waitForFunction(()=>document.querySelector('#performance-selected')?.textContent==='Second Repeater');await page.getByText('Saved observations loaded.',{exact:false}).first().waitFor();assert(!(await section.innerText()).includes('Fixture antenna replacement'));
 await page.locator('#repeater-performance-disclosure > summary').click();const count=requests.filter(r=>r.url.includes('/api/repeater-performance')).length;await page.locator('#managed-repeater').selectOption(key);await page.waitForTimeout(100);assert.equal(requests.filter(r=>r.url.includes('/api/repeater-performance')).length,count);
 assert.equal(errors.length,0,errors.join('\n'));await page.close();
}console.log('Performance Chromium: real local history and persistent journal CRUD, automatic markers, comparisons, SVG markers, 24h/7d/30d histories, responsive chart sizing, names, switching, closed-state isolation and light/dark desktop/mobile passed.');
}catch(e){if(active&&!active.isClosed())await active.screenshot({path:output+'/performance-failure.png'});throw e;}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
