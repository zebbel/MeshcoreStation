const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<html><body><dialog id="companion-dialog" open><div class="companion-grid"><section id="network-settings"></section></div></dialog></body></html>',{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window;
let scopes=[],confirm=true;const calls=[];w.confirm=()=>confirm;
w.fetch=async(url,options)=>{assert.equal(url,'/api/bot/scopes');const body=options.body?JSON.parse(options.body):null;calls.push(body);if(body?.operation==='add')scopes.push({name:body.name,scope_key:'abc'});if(body?.operation==='delete')scopes=[];return {ok:true,json:async()=>({ok:true,scopes,revision:'rev'})}};
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
 w.eval(fs.readFileSync('meshcorestation/web/assets/scopes.js','utf8'));await settle();
 const parent=w.document.getElementById('companion-dialog'),section=w.document.getElementById('scope-settings'),input=w.document.getElementById('scope-name');
 assert.equal(w.document.querySelectorAll('dialog').length,1);assert.equal(section.previousElementSibling.id,'network-settings');
 assert(!w.document.getElementById('scope-save').disabled);
 input.value='region';input.dispatchEvent(new w.Event('input'));confirm=false;
 assert.equal(parent.dispatchEvent(new w.Event('settings-before-close',{cancelable:true})),false);
 w.document.getElementById('scope-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await settle();
 assert.equal(calls.find(c=>c?.operation==='add').name,'region');assert(section.textContent.includes('region'));
 assert(parent.dispatchEvent(new w.Event('settings-before-close',{cancelable:true})));
 confirm=true;[...section.querySelectorAll('button')].find(n=>n.textContent==='Remove').click();await settle();assert.equal(scopes.length,0);
 dom.window.close();console.log('Inline scope loading, save, delete and close guard passed.');
})().catch(e=>{console.error(e);process.exit(1)});
