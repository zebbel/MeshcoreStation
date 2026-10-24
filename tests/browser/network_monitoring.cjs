/* Real Chromium/Leaflet rendering checks, including actual SVG geometry and screenshots. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const root='tests/fixtures/analyzer/responses/',key='769b90b4dd327d7bc9cc651fb8d2f8a4a217957cd36feac6b3216b5acedc36ff',other='ab'.repeat(32);
const files={detail:'node_detail_24h.json',neighbors:'node_neighbors.json',reach:'node_reach_1d.json',metrics:'graph_metrics.json',clock:'clock_skew_24h.json',direct:'direct_packets_24h_empty.json',beacons:'channel_beacons_720h_empty.json',sensors:'channel_sensors_720h_empty.json'};
const captured=Object.fromEntries(Object.entries(files).map(([name,file])=>[name,JSON.parse(fs.readFileSync(root+file))]));
const coords=n=>typeof n.lat==='number'&&typeof n.lon==='number'&&Math.abs(n.lat)<=90&&Math.abs(n.lon)<=180;
const peers=captured.reach.neighbourList.filter(coords),expectedLines=peers.length;
const output=process.env.BROWSER_OUTPUT||'browser-results';fs.mkdirSync(output,{recursive:true});
const sample={ok:true,enabled:true,since:1,profile:{role:'unknown',polling:'manual',next_poll:null,last_error:''},settings:{retention_days:60,neighbor_days:90,summary_days:365,budget_mb:3072,reserve_mb:4096},statistics:{copies:107,ambiguous:0,matching_copies:93,unscoped:50,active_days:1,partial:true,collector_error:'',first_at:1792839600,scope:{},storage:{bytes:0,free_bytes:20e9}},analysis:{recommendations:[],notes:[]},neighbor_snapshots:[],history:[],comparisons:{},repeaters:[{public_key:key,name:'DE_HE_HP_RPT1'},{public_key:other,name:'Second Repeater'}]};
(async()=>{
 const browser=await chromium.launch({headless:true});
 let activePage=null;
 try{
  for(const viewport of [{width:1280,height:960},{width:390,height:844}]){
   for(const colorScheme of ['light','dark']){
    let combinations=false;
    const page=await browser.newPage({viewport,colorScheme}),errors=[];const token=viewport.width+'-'+colorScheme;activePage=page;
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',async route=>{
     const url=new URL(route.request().url());
     if(url.hostname!=='127.0.0.1')return route.abort(); // tile failures must preserve overlays
     if(url.pathname==='/api/repeater-network'){
      const selected=url.searchParams.get('public_key'),data=structuredClone(captured);
      if(combinations){
       const cases=[{weHear:2,theyHear:3,twoWay:true,confidence:'high'},{weHear:2,theyHear:3,twoWay:true,confidence:'low'},{weHear:2,theyHear:0,twoWay:false,confidence:'medium'},{weHear:0,theyHear:4,twoWay:false,confidence:'low'},{weHear:null,theyHear:null,twoWay:null,confidence:'medium'},{weHear:null,theyHear:null,twoWay:null,confidence:'low'},{weHear:1,theyHear:0,twoWay:false,confidence:null},{weHear:2,theyHear:2,twoWay:true,confidence:null},{weHear:null,theyHear:null,twoWay:null,confidence:'unreported'},{weHear:0,theyHear:1,twoWay:false,confidence:'high'},{weHear:0,theyHear:0,twoWay:true,confidence:'low'},{weHear:1,theyHear:null,twoWay:false,confidence:'low'}];
       data.reach.neighbourList=peers.map((n,i)=>({...n,...cases[i]}));
      }
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
    assert(geometry.every(p=>p.length>1&&p.bounds>0&&p.stroke!=='none'&&p.svgHeight>p.mapHeight*.9&&p.maxHeight==='none'),'visible SVG geometry escapes chart sizing rules');
    for(const label of ['Green — Bidirectional connection','Red — Unidirectional connection','Solid line — Medium/high confidence','Dashed line — Low confidence','Gray — Unknown direction','Dotted line — Unknown confidence'])assert.equal(await section.getByText(label,{exact:true}).count(),1);
    async function verifyStyles(){
     const styles=await lines.evaluateAll(paths=>paths.map(p=>({direction:[...p.classList].find(c=>c.startsWith('network-direction-')),confidence:[...p.classList].find(c=>c.startsWith('network-confidence-')),stroke:getComputedStyle(p).stroke,dash:getComputedStyle(p).strokeDasharray,expected:getComputedStyle(p).getPropertyValue(p.classList.contains('network-direction-bidirectional')?'--green':p.classList.contains('network-direction-unidirectional')?'--red':'--muted').trim()})));
     for(const item of styles){
      const expected=await page.evaluate(color=>{const node=document.createElement('span');node.style.color=color;document.body.append(node);const value=getComputedStyle(node).color;node.remove();return value;},item.expected);
      assert.equal(item.stroke,expected);assert.equal(item.dash==='none',['network-confidence-high','network-confidence-medium'].includes(item.confidence));
      if(item.confidence==='network-confidence-low')assert.equal(item.dash,'8px, 7px');
      if(item.confidence==='network-confidence-unknown')assert.equal(item.dash,'2px, 6px');
     }
    }
    await verifyStyles();
    await section.screenshot({path:`${output}/relationships-initial-${token}.png`});
    async function clickLine(line){await line.evaluate(p=>{const point=p.getPointAtLength(p.getTotalLength()/2).matrixTransform(p.getScreenCTM());p.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:point.x,clientY:point.y}));});}
    await clickLine(lines.first());
    const popup=page.locator('.network-connection-popup');await popup.waitFor();
    for(const text of ['DE_HE_HP_RPT1','🐝Heppenheim Nord','weHear: 148','theyHear: 391','Analyzer confidence: high','Distance: 1.5 km','Relationships are inferred from analyzer observations and do not necessarily represent verified direct radio links.'])assert((await popup.innerText()).includes(text));
    await popup.locator('summary').click();assert((await popup.innerText()).includes(key));
    const popupFits=()=>page.waitForFunction(()=>{const popup=document.querySelector('.network-map .leaflet-popup')?.getBoundingClientRect(),map=document.querySelector('.network-map')?.getBoundingClientRect();return popup&&map&&popup.top>=map.top-1&&popup.bottom<=map.bottom+1&&popup.left>=map.left-1&&popup.right<=map.right+1&&(()=>{const controls=document.querySelector('.network-map .leaflet-control-zoom').getBoundingClientRect();return popup.right<=controls.left||popup.left>=controls.right||popup.bottom<=controls.top||popup.top>=controls.bottom;})();});
    await popupFits();
    await page.setViewportSize({width:viewport.width===390?844:390,height:viewport.height});await section.scrollIntoViewIfNeeded();await popupFits();
    await page.setViewportSize(viewport);await section.scrollIntoViewIfNeeded();await popupFits();
    await section.screenshot({path:`${output}/relationship-popup-${token}.png`});await page.locator('.network-map .leaflet-popup-close-button').click();await popup.waitFor({state:'detached'});
    const before=await lines.first().getAttribute('d');await page.locator('.network-map .leaflet-control-zoom-in').click();
    await page.waitForFunction(d=>document.querySelector('.network-map path.network-relationship')?.getAttribute('d')!==d,before);
    await page.waitForFunction(()=>!document.querySelector('.network-map').classList.contains('leaflet-zoom-anim'));
    const canvas=await page.locator('.network-map').boundingBox();await page.mouse.move(canvas.x+canvas.width*.6,canvas.y+canvas.height*.5);await page.mouse.down();await page.mouse.move(canvas.x+canvas.width*.6+40,canvas.y+canvas.height*.5+20,{steps:8});await page.mouse.up();
    await section.screenshot({path:`${output}/relationships-${token}.png`});
    for(const id of ['optimization-analysis-disclosure','repeater-network-disclosure']){
     const padding=await page.locator('#'+id+' > .optimizer-section-body').evaluate(n=>({left:getComputedStyle(n).paddingLeft,right:getComputedStyle(n).paddingRight}));assert.deepEqual(padding,gutter);
    }
    assert(await page.locator('.network-route').first().innerText().then(t=>t.includes('DE_HE_HP_RPT1')&&t.includes('🐝Heppenheim Nord')&&t.includes('Hemsbergturm')));
    assert.equal(await page.locator('.network-route-table td').nth(2).evaluate(n=>getComputedStyle(n).whiteSpace),'nowrap');
    assert(!await page.locator('.network-route').first().locator('..').locator('..').innerText().then(t=>t.includes('Not recorded')),'captured path timestamps remain readable');
    await page.getByRole('heading',{name:'Packet path patterns (potential hash ambiguity)',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:`${output}/packet-paths-${token}.png`});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no dashboard horizontal overflow');
    await page.locator('#repeater-network-disclosure > summary').click();await page.locator('#repeater-network-disclosure > summary').click();await lines.first().waitFor();assert.equal(await page.locator('.network-map.leaflet-container').count(),1);
    await page.setViewportSize({width:viewport.width===390?430:1180,height:viewport.height});await section.scrollIntoViewIfNeeded();assert.equal(await lines.count(),expectedLines);
    combinations=true;await page.locator('#network-refresh').click();await page.locator('.network-map path.network-confidence-unknown').first().waitFor();await section.scrollIntoViewIfNeeded();await verifyStyles();
    for(const direction of ['bidirectional','unidirectional','unknown'])for(const confidence of ['low','unknown'])assert(await page.locator(`.network-map .network-direction-${direction}.network-confidence-${confidence}`).count()>0);
    await section.screenshot({path:`${output}/relationship-combinations-${token}.png`});
    await clickLine(page.locator('.network-map .network-direction-unidirectional.network-confidence-low').first());await popup.waitFor();assert((await popup.innerText()).includes('Selected repeater → connected repeater (theyHear).'));assert((await popup.innerText()).includes('weHear: 0'));assert((await popup.innerText()).includes('theyHear: 4'));await page.locator('.network-map .leaflet-popup-close-button').click();await popup.waitFor({state:'detached'});
    await clickLine(page.locator('.network-map .network-direction-unknown.network-confidence-unknown').first());await popup.waitFor();assert((await popup.innerText()).includes('Confidence unknown; dotted line.'));await page.locator('.network-map .leaflet-popup-close-button').click();await popup.waitFor({state:'detached'});
    await page.locator('#managed-repeater').selectOption(other);await page.waitForFunction(()=>document.querySelector('#network-selected')?.textContent.includes('Second Repeater'));await lines.first().waitFor();assert.equal(await page.locator('.network-map.leaflet-container').count(),1);
    assert.equal(errors.length,0,errors.join('\n'));await page.close();
   }
  }
  console.log('Real Chromium: desktop/mobile, light/dark, named paths, matched gutters, SVG geometry, divIcon markers, zoom/pan/resize, tile failures, reopen and repeater switching passed.');
 }catch(e){if(activePage&&!activePage.isClosed()){await activePage.screenshot({path:output+'/failure.png'});fs.writeFileSync(output+'/failure.html',await activePage.content());}throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
