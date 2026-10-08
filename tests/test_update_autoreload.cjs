const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
for(const [page,phase,target,expected] of [['old','complete','new',1],['new','complete','new',0],['old','failed','new',0],['old','complete','other',0]]){
 const dom=new JSDOM(`<html><head><meta name="meshcorestation-revision" content="${page}"></head><body><div id="companion-dialog"><div class="companion-grid"></div></div></body></html>`,{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window;
 w.AbortSignal.timeout=()=>undefined;w.reloadCount=0;
 w.fetch=async()=>({ok:true,json:async()=>({ok:true,revision:'new',version:'2.3.0',ready:true,check:{},status:{phase,target}})});
 w.eval(fs.readFileSync('meshcorestation/web/assets/updates.js','utf8').replaceAll('location.reload()','window.reloadCount++'));
 await settle();assert.equal(w.reloadCount,expected);
 w.document.querySelector('.update-check').click();await settle();assert.equal(w.reloadCount,expected);
 dom.window.close();
}
console.log('Update auto-reload, loop prevention and rollback checks passed.');
})().catch(e=>{console.error(e);process.exit(1)});
