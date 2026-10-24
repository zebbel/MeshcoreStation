const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<body></body>',{url:'http://localhost',runScripts:'outside-only'}),w=dom.window;
w.fetch=()=>{throw Error('Name lookups must never request network data')};w.eval(fs.readFileSync('meshcorestation/web/assets/ab_repeater_names.js','utf8'));
const names=w.MeshcoreStationRepeaterNames,A='76'.repeat(32),B='e5'.repeat(32),C='76'.repeat(4)+'aa'.repeat(28),unknown='32'.repeat(32);
(async()=>{
 names.ingest([{public_key:A,name:'Hill'},{public_key:B,name:'City'}]);
 assert.equal(names.label(A.toUpperCase()),'Hill');assert.equal(names.label(unknown),'Unknown Repeater (32323232…)');
 assert(names.label(A.slice(0,8)).includes('unresolved prefix'),'even a unique known prefix is not confirmed');
 names.ingest([{public_key:C,name:'Hill'}]);assert.notEqual(names.label(A),names.label(C));assert(names.label(A).startsWith('Hill ('));
 const n=names.element(A);w.document.body.append(n);assert.equal(n.title,A);
 const chosen=names.element(B,'option');chosen.value=B;w.document.body.append(chosen);
 names.ingest([{pubkey:A,name:'Wrong external name'}],'analyzer');assert(names.label(A).startsWith('Hill'));
 names.ingest([{public_key:A,name:'Updated Hill'}]);await new Promise(r=>setImmediate(r));assert.equal(n.textContent,'Updated Hill');assert.equal(names.label(C),'Hill');assert.equal(chosen.value,B);
 names.ingest([{ID:unknown,Name:'<img onerror="bad()">'}],'analyzer');assert.equal(names.element(unknown).querySelector('img'),null);
 names.ingest([{public_key:'a'.repeat(64),name:'Unnamed repeater'}]);assert(names.label('a'.repeat(64)).startsWith('Unknown Repeater'));
 names.ingest([{public_key:A.slice(0,8),name:'Guessed name'}]);assert(names.label(A.slice(0,8)).includes('unresolved prefix'));
 dom.window.close();console.log('Reusable names: exact keys, duplicate labels, safe fallbacks, no prefix guessing, source priority, tooltips and live updates passed.');
})().catch(e=>{console.error(e);process.exit(1)});
