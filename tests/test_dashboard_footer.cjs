const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const settle=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
(async()=>{for(const mode of ['current','available','error']){
 const dom=new JSDOM('<body><footer id="dashboard-footer"><span id="footer-copyright"></span><span id="footer-version"></span><span id="footer-firmware"></span><span id="footer-update"></span><button hidden id="footer-update-button"></button></footer>',{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window,$=id=>w.document.getElementById(id),calls=[];let opened;
 w.AbortSignal.timeout=()=>undefined;w.setInterval=()=>{throw Error('No footer polling');};w.meshcorestationOpenInstalledUpdate=result=>opened=result;
 w.fetch=async(url,options)=>{const body=options.body?JSON.parse(options.body):null;calls.push({url,body});
  if(url.includes('firmware'))return {ok:true,json:async()=>({ok:true,connected:mode!=='error',device:{ver:'1.14',fw_build:'build-123'}})};
  if(body){assert.deepEqual(body,{action:'check',branch:'v4.0.0'});if(mode==='error')throw Error('GitHub unavailable');return {ok:true,json:async()=>({ok:true,check:{branch:'v4.0.0',available:mode==='available',ready:true,latest:'b'.repeat(40)}})};}
  return {ok:true,json:async()=>({ok:true,version:'4.3.3',branch:'v4.0.0',revision:'a'.repeat(40),ready:true})};};
 w.eval(fs.readFileSync('meshcorestation/web/assets/dashboard_footer.js','utf8'));await settle();
 assert.equal(calls.length,3);assert.equal(calls.filter(c=>c.body).length,1);assert($('footer-copyright').textContent.includes(`${new Date().getFullYear()} zebbel`));assert($('footer-version').textContent.includes('4.3.3 · v4.0.0'));
 assert.equal($('footer-update-button').hidden,mode!=='available');assert.equal($('footer-update').textContent,mode==='current'?'Up to date':mode==='available'?'New revision available':'Update check unavailable');
 assert.equal($('footer-firmware').textContent,mode==='error'?'Companion firmware unavailable':'Companion firmware 1.14 · build-123');
 if(mode==='available'){$('footer-update-button').click();assert.equal(opened.branch,'v4.0.0');assert.equal(opened.check.available,true);assert.equal(calls.length,3,'opening updater does not install or check another branch');}
 dom.window.close();
 }console.log('Footer installed-branch check, update handoff, firmware, unavailable services and no automatic install/polling passed.');
})().catch(e=>{console.error(e);process.exit(1);});
