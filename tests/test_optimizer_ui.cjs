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
notes:[]},neighbor_snapshots:[],history:[],comparisons:{}};
w.fetch=async (url,opts)=>{reqs.push({url,method:opts.method,body:opts.body});return {
ok:true,json:async()=>sample}};
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
w.eval(script);
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
assert.equal(posts.length,1);assert.equal(posts[0].type,'meshcorestation-optimizer-ready');
w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:parent,
 data:{type:'meshcorestation-optimizer-context',public_key:key,name:'Hill'}}));
await settle();
assert.equal(reqs.length,1);assert.equal(reqs[0].method,'GET');
assert.equal(posts.length,1); // no LoRa on opening
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
dom.window.close();
console.log('Optimizer passive GET/analysis, explicit polling opt-in and manual LoRa button passed.');
})().catch(e=>{console.error(e);process.exit(1)});
