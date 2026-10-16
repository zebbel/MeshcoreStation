/* Dash loads every asset stylesheet, so standalone page CSS must stay scoped. */
const fs=require('fs'), assert=require('assert'), {JSDOM}=require('jsdom');
const css=fs.readFileSync('meshcorestation/web/assets/rooms.css','utf8');
const dom=new JSDOM('<style>'+css+'</style><main><section><form><label>Value<input></label></form></section></main>');
function check(rules){
 for(const rule of rules){
  if(rule.selectorText) for(const selector of rule.selectorText.split(','))
   assert(selector.trim().startsWith('.rooms-page '),'Unscoped room selector: '+selector);
  if(rule.cssRules)check(rule.cssRules);
 }
}
check(dom.window.document.styleSheets[0].cssRules);
const style=dom.window.getComputedStyle(dom.window.document.querySelector('section'));
assert(!style.borderTopWidth || style.borderTopWidth==='0px','Room border leaks onto dashboard sections');
const room=new JSDOM(fs.readFileSync('meshcorestation/web/rooms.html','utf8'));
assert(room.window.document.body.classList.contains('rooms-page'));
assert.deepEqual([...room.window.document.querySelectorAll('link[rel=stylesheet]')].map(x=>x.getAttribute('href')),['/assets/style.css','/assets/rooms.css']);
assert(!css.includes('color-scheme:dark'));
dom.window.close();room.window.close();
console.log('Room styles are scoped and reuse the dashboard theme.');
