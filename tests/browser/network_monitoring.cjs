/* Real Chromium/Leaflet rendering checks, including actual SVG geometry and screenshots. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const root='tests/fixtures/analyzer/responses/',key='769b90b4dd327d7bc9cc651fb8d2f8a4a217957cd36feac6b3216b5acedc36ff',other='ab'.repeat(32);
const files={detail:'node_detail_24h.json',neighbors:'node_neighbors.json',reach:'node_reach_1d.json',metrics:'graph_metrics.json',clock:'clock_skew_24h.json',direct:'direct_packets_24h_empty.json',beacons:'channel_beacons_720h_empty.json',sensors:'channel_sensors_720h_empty.json'};
const captured=Object.fromEntries(Object.entries(files).map(([name,file])=>[name,JSON.parse(fs.readFileSync(root+file))]));
const coords=n=>typeof n.lat==='number'&&typeof n.lon==='number'&&Math.abs(n.lat)<=90&&Math.abs(n.lon)<=180;
const peers=captured.reach.neighbourList.filter(coords),expectedLines=peers.filter(n=>n.weHear>0||n.theyHear>0||n.twoWay===true).length;
const output=process.env.BROWSER_OUTPUT||'browser-results';fs.mkdirSync(output,{recursive:true});
const sample={ok:true,enabled:true,since:1,profile:{role:'unknown',polling:'manual',next_poll:null,last_error:''},settings:{retention_days:60,neighbor_days:90,summary_days:365,budget_mb:3072,reserve_mb:4096},statistics:{copies:107,ambiguous:0,matching_copies:93,unscoped:50,active_days:1,partial:true,collector_error:'',first_at:1792839600,scope:{},storage:{bytes:0,free_bytes:20e9}},analysis:{recommendations:[],notes:[]},neighbor_snapshots:[],history:[],comparisons:{},repeaters:[{public_key:key,name:'DE_HE_HP_RPT1'},{public_key:other,name:'Second Repeater'}]};
(async()=>{
 const browser=await chromium.launch({headless:true});
 let activePage=null;
 try{
  for(const viewport of [{width:1280,height:960},{width:390,height:844}]){
   for(const colorScheme of ['light','dark']){
    const page=await browser.newPage({viewport,colorScheme}),errors=[];const token=viewport.width+'-'+colorScheme;activePage=page;
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',async route=>{
     const url=new URL(route.request().url());
     if(url.hostname!=='127.0.0.1')return route.abort(); // tile failures must preserve overlays
     if(url.pathname==='/api/repeater-network'){
      const selected=url.searchParams.get('public_key'),data=structuredClone(captured);
      if(selected===other){data.detail.node.id=other;data.detail.node.name='Second Repeater';data.detail.node.lat=49.7;data.metrics.id=other;}
      return route.fulfill({json:{ok:true,public_key:selected,experimental:true,live_verified:false,state:'available',fetched_at:1792839600,stale:false,data,repeaters:sample.repeaters}});
     }
     if(url.pathname==='/api/repeater-optimizer')return route.fulfill({json:sample});
     return route.continue();
    });
    await page.goto('http://127.0.0.1:8050');
    await page.locator('#repeater-management-disclosure > summary').click();
    await page.waitForFunction(k=>document.querySelector('#managed-repeater')?.value===k,key);
    await page.locator('#repeater-optimizer-disclosure > summary').click();
    await page.locator('#repeater-statistics-disclosure > summary').click();
    await page.locator('#repeater-statistics-inline .stats-detailed > summary').click();
    await page.locator('.stats-content .stats-metric').first().waitFor();
    const gutter=await page.locator('#repeater-statistics-disclosure .optimizer-section-body').evaluate(n=>({left:getComputedStyle(n).paddingLeft,right:getComputedStyle(n).paddingRight}));
    await page.locator('#repeater-statistics-disclosure').screenshot({path:`${output}/statistics-${token}.png`});
    await page.locator('#optimization-analysis-disclosure > summary').click();
    await page.frameLocator('#repeater-advisor-frame').locator('#optimizer-content:not([hidden])').waitFor();
    await page.waitForFunction(()=>Number.parseFloat(document.querySelector('#repeater-advisor-frame').style.height)>500);
    const frame=page.frameLocator('#repeater-advisor-frame');
    assert(await frame.locator('main').evaluate(n=>document.documentElement.scrollWidth<=innerWidth+1),'iframe has no horizontal page overflow');
    const fit=await page.locator('#repeater-advisor-frame').evaluate(n=>Math.abs(n.getBoundingClientRect().height-n.contentDocument.querySelector('main').getBoundingClientRect().height));
    assert(fit<=4,'iframe height follows actual rendered content');
    await page.locator('#optimization-analysis-disclosure').screenshot({path:`${output}/analysis-${token}.png`});
    await page.locator('#repeater-network-disclosure > summary').click();
    const lines=page.locator('.network-map path.network-relationship');await lines.first().waitFor();
    assert.equal(await lines.count(),expectedLines);
    assert.equal(await page.locator('.network-map .leaflet-marker-icon').count(),peers.length+1);
    assert.equal(await page.locator('.network-map img.leaflet-marker-icon').count(),0,'no missing image-based markers');
    const section=page.locator('#network-content .stats-section').filter({has:page.getByRole('heading',{name:'Observable relationships',exact:true})});
    await section.scrollIntoViewIfNeeded();
    const geometry=await lines.evaluateAll(paths=>paths.map(p=>({length:p.getTotalLength(),bounds:p.getBBox().width+p.getBBox().height,stroke:getComputedStyle(p).stroke,dashes:getComputedStyle(p).strokeDasharray,svgHeight:p.ownerSVGElement.getBoundingClientRect().height,maxHeight:getComputedStyle(p.ownerSVGElement).maxHeight,mapHeight:p.closest('.network-map').clientHeight})));
    assert(geometry.every(p=>p.length>1&&p.bounds>0&&p.stroke!=='none'&&p.dashes!=='none'&&p.svgHeight>p.mapHeight*.9&&p.maxHeight==='none'),'visible SVG geometry escapes chart sizing rules');
    const before=await lines.first().getAttribute('d');await page.locator('.network-map .leaflet-control-zoom-in').click();
    await page.waitForFunction(d=>document.querySelector('.network-map path.network-relationship')?.getAttribute('d')!==d,before);
    await page.waitForFunction(()=>!document.querySelector('.network-map').classList.contains('leaflet-zoom-anim'));
    const canvas=await page.locator('.network-map').boundingBox();await page.mouse.move(canvas.x+canvas.width*.6,canvas.y+canvas.height*.5);await page.mouse.down();await page.mouse.move(canvas.x+canvas.width*.6+40,canvas.y+canvas.height*.5+20,{steps:8});await page.mouse.up();
    await section.screenshot({path:`${output}/relationships-${token}.png`});
    for(const id of ['optimization-analysis-disclosure','repeater-network-disclosure']){
     const padding=await page.locator('#'+id+' > .optimizer-section-body').evaluate(n=>({left:getComputedStyle(n).paddingLeft,right:getComputedStyle(n).paddingRight}));assert.deepEqual(padding,gutter);
    }
    assert(await page.locator('.network-route').first().innerText().then(t=>t.includes('DE_HE_HP_RPT1')&&t.includes('🐝Heppenheim Nord')&&t.includes('Hemsbergturm')));
    assert(!await page.locator('.network-route').first().locator('..').locator('..').innerText().then(t=>t.includes('Not recorded')),'captured path timestamps remain readable');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no dashboard horizontal overflow');
    await page.locator('#repeater-network-disclosure > summary').click();await page.locator('#repeater-network-disclosure > summary').click();await lines.first().waitFor();assert.equal(await page.locator('.network-map.leaflet-container').count(),1);
    await page.setViewportSize({width:viewport.width===390?430:1180,height:viewport.height});await section.scrollIntoViewIfNeeded();assert.equal(await lines.count(),expectedLines);
    await page.locator('#managed-repeater').selectOption(other);await page.waitForFunction(()=>document.querySelector('#network-selected')?.textContent.includes('Second Repeater'));await lines.first().waitFor();assert.equal(await page.locator('.network-map.leaflet-container').count(),1);
    assert.equal(errors.length,0,errors.join('\n'));await page.close();
   }
  }
  console.log('Real Chromium: desktop/mobile, light/dark, named paths, matched gutters, SVG geometry, divIcon markers, zoom/pan/resize, tile failures, reopen and repeater switching passed.');
 }catch(e){if(activePage&&!activePage.isClosed()){await activePage.screenshot({path:output+'/failure.png'});fs.writeFileSync(output+'/failure.html',await activePage.content());}throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
