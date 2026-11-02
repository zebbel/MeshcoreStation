/* Reproducible actual-browser acceptance. Uses serve.py's synthetic fixture only. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
fs.mkdirSync('browser-evidence',{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true});try{
 for(const [width,height,colorScheme] of [[1280,960,'light'],[390,844,'dark']]){
  const page=await browser.newPage({viewport:{width,height},colorScheme}),errors=[];
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
  await page.locator('#open-channels').click();await page.locator('#channels-list li').first().waitFor();assert(await page.locator('#channels-list').innerText().then(t=>t.includes('Bot')));await page.locator('#channels-list button[aria-label^="Use "][data-protected="false"]').first().click();await page.locator('#channels-list button.channel-delete[disabled]').waitFor();await page.locator('#channels-close').click();
  await page.locator('#open-contacts').click();await page.locator('.contact-manage').first().click();await page.locator('#repeater-login-dialog[open]').waitFor();await page.locator('#repeater-login-form button[type="submit"]').click();await page.locator('#repeater-manage-dialog[open]').waitFor();assert.equal(await page.locator('#repeater-manage-dialog [role="tab"]').count(),3);await page.locator('#repeater-tab-console').click();assert(await page.locator('#repeater-console-command').isDisabled());await page.locator('#repeater-close').click();await page.locator('#contacts-close').click();
  await page.locator('#bot-disclosure > summary').click();await page.locator('#command-history-disclosure > summary').click();await page.waitForFunction(()=>document.querySelectorAll('#command-rows tr[data-row-id]').length===200);await page.locator('#load-older').click();await page.waitForFunction(()=>document.querySelectorAll('#command-rows tr[data-row-id]').length===205);
  await page.locator('#command-rows button[data-details]').last().click();await page.locator('#details-dialog[open]').waitFor();await page.locator('#reply-tracking').getByText('Outgoing replies',{exact:true}).waitFor();await page.locator('#close-details').click();
  await page.locator('#open-commands-history').click();await page.locator('#commands-dialog[open]').waitFor();await page.locator('#commands-close').click();
  await page.locator('#open-repeaters').click();await page.locator('#repeater-map .leaflet-marker-icon').first().waitFor();await page.locator('#close-repeaters').click();
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('V5 actual-browser desktop/mobile layout, modal hosts, contact Manage, protected Bot channel, nested 200-row paging, details and offline registry map passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
