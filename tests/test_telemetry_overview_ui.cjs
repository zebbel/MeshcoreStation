const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<details id="repeater-management-disclosure" open><div id="battery-overview"></div></details>',{runScripts:'outside-only',url:'http://localhost/',pretendToBeVisual:true}),w=dom.window,d=w.document;
const key='ab'.repeat(32),end=1700000000,calls=[];w.meshcorestationSelectedRepeater=key;w.setInterval=()=>1;
const sample={sampled_at:end-100,voltage:3.92,temperature:24.6,temperature_channel:3,interval_seconds:1800};
w.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>({ok:true,config:{public_key:key,timezone:'Europe/Berlin',temperature_channel:3},repeaters:[{public_key:key,name:'Hill'}],latest:sample,latest_temperature:sample,samples:[sample],temperature_samples:[sample],server_time:end})};};
for(const file of ['aa_display','ab_battery','battery_overview'])w.eval(fs.readFileSync('meshcorestation/web/assets/'+file+'.js','utf8'));
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
 await settle();assert(d.getElementById('battery-overview-latest').textContent.includes('3.92 V'));
 assert(d.getElementById('temperature-overview-latest').textContent.includes('24.6 °C'));
 assert.equal(d.querySelectorAll('svg').length,0,'Collapsed charts defer rendering');
 for(const id of ['battery-chart-disclosure','temperature-chart-disclosure']){const section=d.getElementById(id);section.open=true;section.dispatchEvent(new w.Event('toggle'));}
 assert.equal(d.querySelectorAll('svg').length,2);
 for(const days of ['7','30']){const picker=d.getElementById('battery-overview-days');picker.value=days;picker.dispatchEvent(new w.Event('change'));await settle();assert(calls.at(-1).includes('days='+days));}
 const temp=d.querySelector('#temperature-overview-chart svg');temp.dispatchEvent(new w.MouseEvent('click',{clientX:900,clientY:100}));
 assert.equal(temp.querySelector('.telemetry-selected-value').textContent,'24.6 °C');
 d.getElementById('repeater-management-disclosure').open=false;
 const count=calls.length;d.dispatchEvent(new w.CustomEvent('managed-repeater-selected'));await settle();assert.equal(calls.length,count,'Closed telemetry panel must not poll');
 dom.window.close();console.log('Telemetry overview latest values, separate lazy charts and shared 24h/7d/30d period passed.');
})().catch(error=>{console.error(error);dom.window.close();process.exit(1)});
