/* Independent status view: no radio requests, no collection toggles or charts. */
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<body><select id="managed-repeater"><option value="management">Management choice</option></select><details id="repeater-statistics-disclosure"><select id="statistics-repeater"></select><p id="statistics-status"></p><p id="statistics-error"></p><select id="statistics-period"><option value="1">24 hours</option><option value="7">7 days</option><option value="30">30 days</option></select><button id="statistics-refresh"></button><p id="statistics-view-status"></p><p id="statistics-coverage"></p><div id="statistics-hourly"></div><div id="statistics-hops"></div><div id="statistics-regions"></div></details></body>',{url:'http://localhost',runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window,$=id=>w.document.getElementById(id),A='aa'.repeat(32),B='bb'.repeat(32);let requests=[],pending=null,mode='ok';
w.fetch=async(url,options)=>{
 requests.push({url,options});assert(url.startsWith('/api/repeater-statistics/')); assert.equal(options.method,undefined);
 if(mode==='pending')return new Promise(resolve=>{pending=resolve;});
 if(mode==='error')throw Error('Temporary failure');
 const selected=url.includes(B)?B:A;
 if(url.includes('/view?'))return {ok:true,json:async()=>({ok:true,selected,days:Number(new URL(url,'http://localhost').searchParams.get('days'))})};
 return {ok:true,json:async()=>({ok:true,repeaters:[{public_key:A,name:'Alpha'},{public_key:B,name:'Beta'}],selected,observation_count:selected===A?3:9,last_recorded_at:2000000000,error:'',health:{running:true,connected:true,dropped:0,invalid:0,error:'',repeater_error:''}})};
};
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));};
let rendered=[];w.MeshcoreStationStatisticsVisuals={render:data=>rendered.push(data),dispose:()=>{}};
(async()=>{try{
 w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_statistics.js','utf8'));await settle();assert.equal(requests.length,0,'collapsed view does not request status');
 $('repeater-statistics-disclosure').open=true;await settle();assert.equal($('statistics-repeater').options.length,2);assert($('statistics-status').textContent.includes('3 saved observations'));
 $('statistics-repeater').value=B;$('statistics-repeater').dispatchEvent(new w.Event('change'));await settle();assert($('statistics-status').textContent.includes('9 saved observations'));assert.equal($('managed-repeater').value,'management','statistics has independent selection');
 $('statistics-period').value='7';$('statistics-period').dispatchEvent(new w.Event('change'));await settle();assert.equal(rendered.at(-1).days,7);assert.equal(rendered.at(-1).selected,B);
 $('statistics-refresh').click();await settle();assert.equal(rendered.at(-1).days,7,'manual refresh preserves shared period');
 mode='error';$('statistics-repeater').dispatchEvent(new w.Event('change'));await settle();assert.equal($('statistics-error').textContent,'Temporary failure');assert($('statistics-status').textContent.includes('9 saved observations'),'errors do not replace saved count with zero');
 mode='ok';$('statistics-repeater').dispatchEvent(new w.Event('change'));await settle();assert(requests.at(-1).url.includes(B),'transient errors preserve viewed repeater');
 mode='pending';$('statistics-repeater').value=A;$('statistics-repeater').dispatchEvent(new w.Event('change'));await settle();const inFlight=requests.at(-1);$('repeater-statistics-disclosure').open=false;await settle();assert(inFlight.options.signal.aborted);
 pending({ok:true,json:async()=>({ok:true,repeaters:[],selected:'',health:{}})});await settle();assert($('statistics-status').textContent.includes('9 saved observations'),'late response from closed section ignored');
 const count=requests.length;w.document.dispatchEvent(new w.CustomEvent('managed-repeater-removed',{detail:A}));await settle();assert.equal(requests.length,count,'membership event while collapsed does not request status');
 console.log('Statistics independent selector, shared periods, saved refresh, no background polling, error preservation and stale-response cancellation passed.');
}finally{dom.window.close();}})().catch(e=>{console.error(e);process.exit(1);});
