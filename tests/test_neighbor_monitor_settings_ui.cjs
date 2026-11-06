const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
const A='aa'.repeat(32),dom=new JSDOM(`<details id="repeater-statistics-disclosure"><select id="statistics-repeater"></select><select id="statistics-period"><option value="1">24h</option></select><button id="statistics-refresh"></button><p id="statistics-status"></p><p id="statistics-error"></p><fieldset id="neighbor-monitor-settings" disabled><span id="neighbor-monitor-checkbox-host"></span><input id="neighbor-monitor-interval"><button id="neighbor-monitor-save"></button><p id="neighbor-monitor-status"></p><button id="neighbor-monitor-recheck"></button><div id="neighbor-monitor-protocol-details"></div></fieldset></details>`,{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost'}),w=dom.window,d=w.document;
let enabled=false,saves=0,rechecks=0;w.AbortSignal.timeout=()=>undefined;
w.fetch=async(url,opts)=>{
 if(url.includes('neighbor-monitor')){
  assert.equal(opts.headers['X-Meshcore-Control'],'1');
  if(opts.method==='POST'){const body=JSON.parse(opts.body);assert.equal(body.public_key,A);if(body.operation==='recheck_protocol'){rechecks++;}else{assert.equal(body.interval_minutes,30);enabled=body.enabled;saves++;}}
  return {ok:true,json:async()=>({ok:true,config:{public_key:A,enabled,interval_minutes:30,state:'waiting'},protocol:{capability:'averaged',detection:'supported',completeness:'partial',records_retrieved:12,duration_seconds:68,session:'01',diagnostics:{expired:2,retained:4,newest_window:3},warning:'Continuation saved'},running:true})};
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
 assert(d.getElementById('neighbor-monitor-protocol-details').textContent.includes('Detected SNR protocol: Averaged'));
 assert(d.getElementById('neighbor-monitor-protocol-details').textContent.includes('Records retrieved: 12'));
 assert(d.getElementById('neighbor-monitor-protocol-details').textContent.includes('Expired: 2'));
 d.getElementById('neighbor-monitor-recheck').click();await settle();assert.equal(rechecks,1);assert.equal(saves,2);assert(!enabled);assert(d.getElementById('neighbor-monitor-status').textContent.includes('polling interval is unchanged'));
 d.getElementById('neighbor-monitor-enabled').checked=true;d.getElementById('neighbor-monitor-interval').value='47';
 w.MeshcoreStationRefreshSavedSnr();await settle();
 assert(d.getElementById('neighbor-monitor-enabled').checked);assert.equal(d.getElementById('neighbor-monitor-interval').value,'47');assert.equal(saves,2,'Manual completion refresh must not save or reset automatic controls');
 console.log('Opt-in per-repeater settings load/save, local request protection and enable/disable readback passed.');
}finally{w.close();}})().catch(e=>{console.error(e);process.exit(1)});
