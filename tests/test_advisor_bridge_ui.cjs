const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<body></body>',{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window;
w.TextEncoder=TextEncoder;w.confirm=()=>true;
w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
const key='ab'.repeat(32),posts=[],replies=[],fields=['flood.max','flood.max.unscoped','flood.max.advert','advert.interval','flood.advert.interval','loop.detect'];
let values=Object.fromEntries(fields.map(f=>[f,f==='loop.detect'?'minimal':'32'])),fail=false;
const popup={closed:false,postMessage:data=>replies.push(data)};w.open=()=>popup;
w.fetch=async(url,options)=>{const b=JSON.parse(options.body);posts.push(b);let r={};
if(b.action==='login')r={session:'token',admin:true,contact:{public_key:key},fields:Object.fromEntries(fields.map(f=>[f,{section:'routing',label:f,kind:'text',limit:20}]))};
else if(b.action==='read')r={value:values[b.field]};
else if(b.action==='advisor_write'){if(fail)return {ok:false,json:async()=>({ok:false,error:'timed out'})};values[b.field]=b.value;r={value:b.value};}
else r={data:{},contact:{public_key:key},sampled_at:1};return {ok:true,json:async()=>({ok:true,...r})};};
w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_management.js','utf8'));
const $=id=>w.document.getElementById(id),settle=()=>new Promise(r=>setImmediate(r));
const send=(type,extra={})=>w.dispatchEvent(new w.MessageEvent('message',{origin:'http://localhost',source:popup,data:{type:'meshcorestation-advisor-'+type,request_id:1,...extra}}));
(async()=>{
w.meshcorestationManageRepeater({public_key:key,name:'Hill',type:2});$('repeater-login-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await settle();$('repeater-open-advisor').click();
send('request');await settle();assert.equal(replies.at(-1).current['flood.max'],'32');assert(!JSON.stringify(replies).includes('token'));
send('apply',{public_key:'cd'.repeat(32),changes:[{field:'flood.max',value:'16',expected:'32'}]});await settle();assert(replies.at(-1).error.includes('Repeater changed'));
send('apply',{public_key:key,changes:[{field:'flood.max',value:'16',expected:'64'}]});await settle();assert(replies.at(-1).error.includes('changed on the repeater'));assert.equal(posts.filter(p=>p.action==='advisor_write').length,0);
send('apply',{public_key:key,changes:[{field:'flood.max',value:'16',expected:'32'}]});await settle();assert.equal(values['flood.max'],'16');assert.equal(replies.at(-1).results.length,1);
fail=true;const count=posts.length;
send('apply',{public_key:key,changes:[{field:'flood.max',value:'8',expected:'16'},{field:'flood.max.advert',value:'6',expected:'32'}]});await settle();assert.equal(posts.slice(count).filter(p=>p.action==='advisor_write').length,1);assert(replies.at(-1).errors['flood.max']);
w.document.querySelector('[role=tablist]').dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight'}));
// Read via the form then retain a local draft while the advisor reads again.
const config=$('repeater-config');const read=[...config.querySelectorAll('button')].find(b=>b.textContent==='Read'&&b.closest('details').textContent.includes('flood.max'));
read.click();await settle();const field=[...config.querySelectorAll('input')].find(n=>n.value==='16');assert(field);field.value='15';send('request');await settle();assert.equal(field.value,'15');
send('apply',{public_key:key,changes:[{field:'flood.max',value:'8',expected:'16'}]});await settle();assert(replies.at(-1).error.includes('unsaved'));
dom.window.close();console.log('Advisor bridge identity, stale values, partial failure, draft protection and token isolation passed.');
})().catch(e=>{console.error(e);process.exit(1)});
