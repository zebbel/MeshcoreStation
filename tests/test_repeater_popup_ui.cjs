const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<body></body>',{runScripts:'outside-only'}),w=dom.window;
const key='ab'.repeat(32),identity='cd'.repeat(32);let saved=false,posts=[];
w.fetch=async(url,options)=>({ok:true,json:async()=>{
 if(url.includes('/voltage'))return {ok:true,config:{public_key:key}};
 if(options.method==='POST'){posts.push(JSON.parse(options.body));saved=true;}
 return {ok:true,public_key:identity,contacts:saved?[{public_key:key}]:[]};
}});
w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_popup.js','utf8'));
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const box=w.document.createElement('div');w.document.body.append(box);
 w.meshcorestationRepeaterActions(box,{public_key:key,name:'Hill',position:[49,8]},()=>{});
 await settle();const [add,battery]=box.querySelectorAll('button');assert(!add.disabled);assert(battery.disabled);
 add.click();await settle();assert(add.disabled);assert.equal(add.textContent,'Already in contacts');
 assert.equal(posts.length,1);assert.equal(posts[0].expected_public_key,identity);assert.equal(posts[0].value.type,2);assert.equal(posts[0].value.latitude,49);
 const second=w.document.createElement('div');w.meshcorestationRepeaterActions(second,{public_key:key,name:'Hill'},()=>{});await settle();assert(second.querySelector('button').disabled);
 dom.window.close();console.log('Repeater popup contact addition, duplicate prevention and selected battery state passed.');
})().catch(e=>{console.error(e);process.exit(1)});
