const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<body><dialog id="companion-dialog" open><div class="dialog-body"><details id="companion-settings-disclosure"></details></div></dialog></body>',{runScripts:'outside-only',url:'http://localhost/'});
const w=dom.window,$=id=>w.document.getElementById(id),settle=()=>new Promise(r=>setImmediate(r));
let enabled=true,confirm=true,events=0,requests=[];
w.confirm=()=>confirm;
w.addEventListener('meshcorestation-optimizer-state',()=>events++);
w.fetch=async(url,options)=>{
 assert.equal(url,'/api/repeater-optimizer/settings');
 assert.equal(options.headers['X-Meshcore-Control'],'1');
 if(options.body){const b=JSON.parse(options.body);requests.push(b);enabled=b.enabled;}
 return {ok:true,json:async()=>({ok:true,enabled})};
};
w.eval(fs.readFileSync('meshcorestation/web/assets/optimizer_settings.js','utf8'));
(async()=>{
 await settle();assert($('optimizer-enabled').checked);
 assert(!$('optimizer-settings').closest('#companion-settings-disclosure'));
 confirm=false;$('optimizer-enabled').checked=false;$('optimizer-enabled').dispatchEvent(new w.Event('change'));await settle();
 assert.equal(requests.length,0);assert($('optimizer-enabled').checked);
 confirm=true;$('optimizer-enabled').checked=false;$('optimizer-enabled').dispatchEvent(new w.Event('change'));await settle();
 assert.equal(requests.at(-1).confirm,true);assert.equal(enabled,false);assert.equal(events,1);
 assert($('optimizer-settings-message').textContent.includes('collection and scheduled neighbor reads are stopped'));
 $('optimizer-enabled').checked=true;$('optimizer-enabled').dispatchEvent(new w.Event('change'));await settle();
 assert.equal(enabled,true);assert.equal(events,2);
 w.fetch=async()=>{throw Error('Storage unavailable');};
 $('optimizer-enabled').checked=false;$('optimizer-enabled').dispatchEvent(new w.Event('change'));await settle();
 assert($('optimizer-enabled').checked);assert($('optimizer-settings-message').textContent.includes('Reload settings'));
 dom.window.close();console.log('Optimizer settings confirmation, enable/disable, error recovery and independent placement passed.');
})().catch(e=>{console.error(e);process.exit(1)});
