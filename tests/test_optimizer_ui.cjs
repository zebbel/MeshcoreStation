const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const html=fs.readFileSync('meshcorestation/web/repeater_optimizer.html','utf8');
const dom=new JSDOM(html,{runScripts:'outside-only',url:'http://localhost/repeater-optimizer'});
const w=dom.window, $=id=>w.document.getElementById(id);
w.confirm=()=>true;
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
