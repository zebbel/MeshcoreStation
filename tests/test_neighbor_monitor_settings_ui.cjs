const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
const A='aa'.repeat(32),dom=new JSDOM(`<details id="repeater-statistics-disclosure"><select id="statistics-repeater"></select><select id="statistics-period"><option value="1">24h</option></select><button id="statistics-refresh"></button><p id="statistics-status"></p><p id="statistics-error"></p><fieldset id="neighbor-monitor-settings" disabled><span id="neighbor-monitor-checkbox-host"></span><input id="neighbor-monitor-interval"><button id="neighbor-monitor-save"></button><p id="neighbor-monitor-status"></p></fieldset></details>`,{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost'}),w=dom.window,d=w.document;
let enabled=false,saves=0;w.AbortSignal.timeout=()=>undefined;
w.fetch=async(url,opts)=>{
 if(url.includes('neighbor-monitor')){
  assert.equal(opts.headers['X-Meshcore-Control'],'1');
  if(opts.method==='POST'){const body=JSON.parse(opts.body);assert.equal(body.public_key,A);assert.equal(body.interval_minutes,30);enabled=body.enabled;saves++;}
  return {ok:true,json:async()=>({ok:true,config:{public_key:A,enabled,interval_minutes:30,state:'waiting'},running:true})};
 }
 assert(url.includes('/status'));return {ok:true,json:async()=>({ok:true,selected:A,repeaters:[{public_key:A,name:'Selected'}],observation_count:0,health:{running:true,connected:true}})};
};
const settle=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
(async()=>{try{
 w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_statistics.js','utf8'));
 d.getElementById('repeater-statistics-disclosure').open=true;await settle();
 assert(!d.getElementById('neighbor-monitor-settings').disabled);assert(!d.getElementById('neighbor-monitor-enabled').checked);
 d.getElementById('neighbor-monitor-enabled').checked=true;d.getElementById('neighbor-monitor-save').click();await settle();assert.equal(saves,1);assert(d.getElementById('neighbor-monitor-status').textContent.includes('Enabled'));
 d.getElementById('neighbor-monitor-enabled').checked=false;d.getElementById('neighbor-monitor-save').click();await settle();assert.equal(saves,2);assert(d.getElementById('neighbor-monitor-status').textContent.includes('Disabled'));
 console.log('Opt-in per-repeater settings load/save, local request protection and enable/disable readback passed.');
}finally{w.close();}})().catch(e=>{console.error(e);process.exit(1)});
