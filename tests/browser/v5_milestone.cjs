/* Reproducible actual-browser acceptance. Uses serve.py's synthetic fixture only. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
fs.mkdirSync('browser-evidence',{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true});try{
 for(const [width,height,colorScheme] of [[1280,960,'light'],[390,844,'dark']]){
  const page=await browser.newPage({viewport:{width,height},colorScheme,hasTouch:width<800,isMobile:width<800}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  await page.goto('http://127.0.0.1:8050');await page.locator('#bot-status').filter({hasText:'Connected'}).waitFor();
  assert.equal(await page.locator('.cards > section').count(),3);
  const cards=await page.locator('.cards > section').evaluateAll(ns=>ns.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y};}));
  assert(width>800?cards.every(c=>c.y===cards[0].y):cards.every(c=>c.x===cards[0].x)&&cards[0].y<cards[1].y&&cards[1].y<cards[2].y);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert(await page.evaluate(()=>parseFloat(getComputedStyle(document.body).paddingBottom)>=document.querySelector('#dashboard-footer').getBoundingClientRect().height));
  await page.screenshot({path:`browser-evidence/dashboard-${width}-${colorScheme}.png`,fullPage:true});
  await page.locator('#open-station-settings').click();await page.locator('#station-settings-dialog[open] #display-settings').waitFor();assert(await page.locator('#station-settings-dialog #update-panel').isVisible());assert.equal(await page.locator('#station-settings-dialog #bot-serial-port').count(),0);await page.locator('#close-station-settings').click();
  await page.locator('#open-companion').click();await page.locator('#companion-dialog[open] #bot-serial-port').waitFor();await page.locator('#close-companion').click();
  await page.locator('#open-channels').click();await page.locator('#channels-list li').first().waitFor();assert(await page.locator('#channels-list').innerText().then(t=>t.includes('Bot')));await page.locator('#channels-list button[aria-label^="Use "][data-protected="false"]').first().click();await page.locator('#channels-dialog[aria-busy="false"]').waitFor();assert.equal(await page.locator('#channels-list button.channel-delete[data-protected="true"][disabled]').count(),1);await page.locator('#channels-close').click();
  await page.locator('#open-contacts').click();await page.locator('.contact-manage').first().click();await page.locator('#repeater-login-dialog[open]').waitFor();await page.locator('#repeater-login-form button[type="submit"]').click();await page.locator('#repeater-manage-dialog[open]').waitFor();assert.equal(await page.locator('#repeater-manage-dialog [role="tab"]').count(),3);await page.locator('#repeater-tab-console').click();assert(await page.locator('#repeater-console-command').isDisabled());await page.locator('#repeater-close').click();await page.locator('#contacts-close').click();
  await page.locator('#bot-disclosure > summary').click();await page.locator('#command-history-disclosure > summary').click();await page.waitForFunction(()=>document.querySelectorAll('#command-rows tr[data-row-id]').length===200);await page.locator('#load-older').click();await page.waitForFunction(()=>document.querySelectorAll('#command-rows tr[data-row-id]').length===205);
  await page.locator('#command-rows button[data-details]').last().click();await page.locator('#details-dialog[open]').waitFor();await page.locator('#reply-tracking').getByText('Outgoing replies',{exact:true}).waitFor();await page.locator('#close-details').click();
  await page.locator('#open-commands-history').click();await page.locator('#commands-dialog[open]').waitFor();await page.locator('#commands-close').click();
  await page.locator('#open-repeaters').click();await page.locator('#repeater-map .leaflet-marker-icon').first().waitFor();await page.locator('#close-repeaters').click();
  await page.locator('#repeater-statistics-disclosure > summary').click();
  await page.locator('#statistics-repeater option').filter({hasText:'Hill'}).waitFor({state:'attached'});
  assert.equal(await page.locator('#statistics-repeater option').count(),1);
  await page.locator('#statistics-status').filter({hasText:'saved observations'}).waitFor();
  assert(await page.locator('#statistics-repeater').isEnabled());
  await page.locator('#statistics-view-status').filter({hasText:'Saved observations loaded'}).waitFor();
  await page.locator('#statistics-neighbor-map .leaflet-overlay-pane svg path').nth(1).waitFor();
  const overlays=page.locator('#statistics-neighbor-map .leaflet-overlay-pane svg');
  assert(await overlays.evaluate(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0;}));
  assert.equal(await page.locator('#statistics-neighbor-map path[stroke="#15803d"]').count(),1);
  assert.equal(await page.locator('#statistics-neighbor-map path[stroke="#dc2626"]').count(),1);
  // Keep desktop line-click coverage separate from the real touch-marker check.
  // Opening a tall line popup first pans the narrow map and obstructs its markers.
  if(width>800){
   await page.locator('#statistics-neighbor-map path[stroke="#15803d"]').click();
   await page.locator('#statistics-neighbor-map .leaflet-popup-content').filter({hasText:'Last observation'}).waitFor();
   await page.locator('#statistics-neighbor-map .leaflet-popup-close-button').click();
   await page.locator('#statistics-neighbor-map .leaflet-popup').waitFor({state:'hidden'});
  }
  const marker=page.locator('#statistics-neighbor-map .statistics-map-icon[title="Fixture north"]');
  if(width>800){
   await marker.hover();
   await page.locator('.statistics-neighbor-tooltip').filter({hasText:'We hear: 1 times'}).waitFor();
   const counts=page.locator('.statistics-neighbor-tooltip .statistics-neighbor-count');
   assert.deepEqual(await counts.allTextContents(),['We hear: 1 times','They hear: 1 times']);
   assert(await counts.evaluateAll(rows=>rows.every(row=>{const [label,value]=row.children;const a=label.getBoundingClientRect(),b=value.getBoundingClientRect();return Math.abs(a.y-b.y)<2&&b.x>a.x;})),'tooltip label/value pairs stay on one row');
   await page.locator('#statistics-view-status').hover();
   await page.locator('.statistics-neighbor-tooltip').waitFor({state:'hidden'});
   await marker.click();
  }else await marker.tap();
  const popup=page.locator('#statistics-neighbor-map .leaflet-popup-content');
  assert((await popup.textContent()).includes('We hear: 1 times'));
  assert((await popup.textContent()).includes('They hear: 1 times'));
  assert((await popup.textContent()).includes('Last observation'));
  for(const period of ['1','7','30']){
   await page.locator('#statistics-period').selectOption(period);
   await page.locator('#statistics-view-status').filter({hasText:'Saved observations loaded'}).waitFor();
   await page.locator('#statistics-hourly .statistics-hour-bar').first().waitFor({state:'attached'});
   assert.equal(await page.locator('#statistics-hourly circle').count(),0);
   assert(await page.locator('#statistics-hourly .statistics-plot-scroll').evaluate(el=>el.clientWidth>0&&el.scrollWidth>=el.clientWidth));
   assert.equal(await page.locator('#statistics-active-neighbors .statistics-neighbor-bar').count(),4);
   assert(await page.locator('#statistics-heatmap .statistics-heatmap-cell').count()>0);
   assert.equal(await page.locator('#statistics-packet-types .statistics-donut-segment').count(),1);
   assert((await page.locator('#statistics-packet-types').innerText()).includes('100.0%'));
   const pair=await page.locator('#statistics-hops rect[data-hop="2"]').evaluateAll(nodes=>nodes.map(n=>Number(n.getAttribute('x'))));assert(pair[0]<pair[1]);
   const hops=await page.locator('#statistics-hops .statistics-hop-tick').allTextContents();
   assert.deepEqual(hops.map(Number),hops.map(Number).sort((a,b)=>a-b));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  assert(await page.locator('#statistics-regions').innerText().then(t=>t.includes('Unscoped')));
  await page.locator('#statistics-period').selectOption('7');
  await page.locator('#statistics-view-status').filter({hasText:'Saved observations loaded'}).waitFor();
  await page.screenshot({path:`browser-evidence/statistics-${width}-${colorScheme}.png`,fullPage:true});
  await page.locator('#repeater-statistics-disclosure > summary').click();
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('V5 actual-browser desktop/mobile layout, modal hosts, contact Manage, protected Bot channel, nested 200-row paging, details, offline registry map and managed-only Statistics status passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
