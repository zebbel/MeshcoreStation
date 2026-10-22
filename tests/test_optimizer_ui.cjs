const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const html=fs.readFileSync('meshcorestation/web/repeater_optimizer.html','utf8');
const dom=new JSDOM(html,{runScripts:'outside-only',url:'http://localhost/repeater-optimizer'});
const w=dom.window, $=id=>w.document.getElementById(id);
const confirms=[];w.confirm=text=>{confirms.push(text);return true;};
const key='ab'.repeat(32),posts=[],reqs=[];
const parent={closed:false,postMessage:data=>posts.push(data)};
Object.defineProperty(w,'parent',{value:parent,configurable:true});
const sample={ok:true,profile:{role:'unknown',polling:'manual',next_poll:null,last_error:''},
settings:{retention_days:60,neighbor_days:90,summary_days:365,budget_mb:3072,reserve_mb:4096},
statistics:{copies:0,matching_copies:0,unscoped:0,active_days:0,ambiguous:0,
partial:true,collector_error:'',first_at:null,storage:{bytes:0,free_bytes:20e9}},
analysis:{recommendations:[{field:'flood.max',suggested:null,current:null,confidence:'insufficient',
observed:0,matching:0,p90:null,max:null,can_apply:false,reasons:['missing'],explanation:'Not enough evidence.'}],
notes:[]},neighbor_snapshots:[
 {id:3,at:3,source:'manual',reported:2,complete:1,neighbors:[
  {neighbor_key:'1234abcd',snr:2.5,secs_ago:120},
  {neighbor_key:'eeff0011',snr:-3.25,secs_ago:90}]},
 {id:2,at:2,source:'manual',reported:3,complete:0,neighbors:[]},
 {id:1,at:1,source:'manual',reported:0,complete:1,neighbors:[]}
 ],history:[],comparisons:{}};
w.fetch=async (url,opts)=>{reqs.push({url,method:opts.method,body:opts.body});return {
ok:true,json:async()=>sample}};
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
w.eval(script);
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
assert.equal(posts.length,1);assert.equal(posts[0].type,'meshcorestation-optimizer-ready');
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-optimizer-context',public_key:key,name:'Hill'}}));
assert.equal($('load-status').textContent,'Loading optimizer data…');
assert.equal(w.document.querySelector('main').getAttribute('aria-busy'),'true');
assert($('analyze').disabled);
await settle();
assert.equal(reqs.length,1);assert.equal(reqs[0].method,'GET');
assert.equal($('neighbors').querySelectorAll('article').length,1,'Only the most recent read is displayed');
assert($('neighbors').textContent.includes('Prefix 1234abcd'));
assert($('neighbors').textContent.includes('SNR 2.5 dB'));
assert($('neighbors').textContent.includes('2 saved / 2 reported'));
assert(!$('neighbors').textContent.includes('0 saved / 3 reported'),'Older reads are hidden');
assert(!$('neighbors').textContent.includes('Repeater reported no neighbors'),'Old empty reads are hidden');
assert.equal(posts.length,1); // no LoRa on opening
const beforeLocalRefresh=reqs.length;
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-optimizer-refresh'}}));
await settle();
assert.equal(reqs.length,beforeLocalRefresh+1);
assert.equal(reqs.at(-1).method,'GET');
assert.equal(posts.length,1,'Switching tabs must not request LoRa');
$('refresh-neighbors').click();await settle();
assert.equal(reqs.at(-1).method,'GET');
assert.equal(posts.length,1,'Refresh stored snapshots is local only');
$('analyze').click();await settle();
assert.equal(reqs.at(-1).method,'POST');
assert.equal(posts.length,1); // analysis stays local
$('polling').value='12h';$('role').value='regional';$('save-profile').click();
assert.equal(posts.at(-1).type,'meshcorestation-optimizer-profile');
assert.equal(posts.at(-1).polling,'12h');
const requestId=posts.at(-1).request_id;
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-advisor-values',request_id:requestId,saved:true}}));
await settle();
assert.equal($('back'),null);
assert.equal(w.document.querySelectorAll('.scope-field').length,2);
assert.equal(w.document.querySelectorAll('.period-field').length,1);
assert.equal(w.document.querySelectorAll('.storage-field').length,5);
assert.equal(w.document.querySelectorAll('.storage-grid .storage-field').length,5);
for(const id of ['role','polling','days','retention_days','neighbor_days','summary_days','budget_gb','reserve_gb']){
  assert(w.document.querySelector('label[for="'+id+'"]'),'Control needs its own label: '+id);
}
assert.equal($('polling').options[0].textContent,'Manual (default)');
assert.equal($('polling').options[2].textContent,'Every 12 hours');
assert(html.includes('.scope-field select{display:block;width:100%;max-width:none}'));
assert(html.includes('.storage-field input{display:block;width:100%;max-width:none}'));
assert(html.includes('@media(max-width:600px)'));
assert(html.includes('.storage-grid,.kpis{grid-template-columns:1fr}'));
assert(!w.document.body.textContent.includes('Passive by default. Analysis never sends'));
assert.equal($('budget_gb').value,'3');
assert.equal($('reserve_gb').value,'4');
assert.equal($('budget_mb'),null);
assert.equal($('reserve_mb'),null);
assert.equal($('save-storage').textContent,'Save storage limits');
assert.equal($('read-settings').textContent,'Read flood settings');
assert.equal($('analyze').textContent,'Analyze stored observations');
assert.equal($('read-neighbors').textContent,'Read neighbors now');
$('budget_gb').value='3.5';$('reserve_gb').value='4.25';
$('save-storage').click();
let sent=posts.at(-1);
assert.equal(sent.type,'meshcorestation-optimizer-storage');
assert.equal(sent.settings.budget_mb,3584);
assert.equal(sent.settings.reserve_mb,4352);
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-advisor-values',request_id:sent.request_id,saved:true}}));
await settle();
sample.history=[{id:2,at:1,field:'flood.max',before_value:'8',requested:'5',actual:'5',status:'verified'}];
sample.comparisons={'2':{status:'descriptive',message:'Compared.',before:{copies:100},after:{copies:100}}};
$('analyze').click();await settle();
assert.equal($('clear-history').disabled,false);
$('clear-history').click();
sent=posts.at(-1);
assert.equal(sent.type,'meshcorestation-optimizer-clear-history');
assert.equal(sent.confirm,true);
assert(confirms.at(-1).includes('Permanently delete'));
sample.history=[];sample.comparisons={};
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-advisor-values',request_id:sent.request_id,removed:1,saved:true}}));
await settle();
assert.equal($('clear-history').disabled,true);
assert($('history').textContent.includes('No verified optimizer changes'));
$('read-settings').click();
assert.equal(posts.at(-1).type,'meshcorestation-advisor-request');
const readId=posts.at(-1).request_id;
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-advisor-values',request_id:readId,public_key:key,
 current:{'flood.max':'32','flood.max.unscoped':'5'},errors:{}}}));
await settle();
$('read-neighbors').click();
assert.equal(posts.at(-1).type,'meshcorestation-optimizer-neighbors');
const neighborRequest=posts.at(-1).request_id;
sample.neighbor_snapshots.unshift({id:42,at:Date.now()/1000,source:'manual',
 reported:2,complete:1,neighbors:[
 {neighbor_key:'00ffaa11',snr:3.5,secs_ago:12},
 {neighbor_key:'ffcc2211',snr:1.5,secs_ago:14}
]});
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-advisor-values',request_id:neighborRequest,
 snapshot:{id:42,neighbors:2,received:2,reported:2,complete:true}}}));
await settle();
assert($('neighbors').textContent.includes('2 saved / 2 reported'));
assert($('neighbors').textContent.includes('Prefix 00ffaa11'));
assert.equal($('neighbors').querySelectorAll('article').length,1,'A new read replaces the previous entry');
assert(!$('neighbors').textContent.includes('Prefix 1234abcd'),'Previous neighbor read is hidden');
assert.equal($('save-downtime'),null);
assert.equal($('optimizer-content').hidden,false);
// Clearing is explicit and global, then the visible state reloads.
w.fetch=async(url,options)=>{
 const payload=options.body?JSON.parse(options.body):{};
 if(payload.action==='clear'){
   assert.equal(url,'/api/repeater-optimizer/settings');assert.equal(payload.confirm,true);
   sample.neighbor_snapshots=[];sample.history=[];sample.statistics.copies=0;
 }
 return {ok:true,json:async()=>sample};
};
$('clear-storage').click();await settle();
assert(confirms.at(-1).includes('ALL repeaters'));
assert($('message').textContent.includes('storage cleared'));
assert.equal($('neighbors').querySelectorAll('article').length,0);
// Loading feedback stays visible for a slow request and disabled data is hidden.
let finishLoad;
w.fetch=()=>new Promise(resolve=>{finishLoad=resolve;});
$('analyze').click();
assert.equal($('load-status').textContent,'Loading optimizer data…');
assert($('analyze').disabled && $('days').disabled);
finishLoad({ok:true,json:async()=>({ok:true,enabled:false})});await settle();
assert.equal($('optimizer-content').hidden,true);
assert.equal($('disabled-message').hidden,false);
// A failed load provides a working retry without a permanent loading state.
w.fetch=async()=>{throw Error('Network unavailable');};
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-optimizer-refresh'}}));await settle();
assert.equal($('load-status').textContent,'Network unavailable');assert(!$('retry-load').hidden);
w.fetch=async()=>({ok:true,json:async()=>sample});$('retry-load').click();await settle();
assert.equal($('optimizer-content').hidden,false);assert($('retry-load').hidden);
dom.window.close();
console.log('Optimizer passive GET/analysis, explicit polling opt-in and manual LoRa button passed.');
})().catch(e=>{console.error(e);process.exit(1)});
