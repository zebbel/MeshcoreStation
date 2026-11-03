/* Virtual time: independent status/view deadlines, errors and stale snapshots. */
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const html='<details id="repeater-statistics-disclosure"><select id="statistics-repeater"></select><select id="statistics-period"><option value="1">24h</option><option value="7">7d</option></select><button id="statistics-refresh"></button><p id="statistics-status"></p><p id="statistics-error"></p><p id="statistics-view-status"></p><p id="statistics-view-error"></p><div id="statistics-hourly"></div></details>';
const dom=new JSDOM(html,{url:'http://localhost',runScripts:'outside-only',pretendToBeVisual:true}),w=dom.window,$=id=>w.document.getElementById(id),key='aa'.repeat(32);
let clock=0,next=0,timers=new Map(),pendingStatus,pendingView,viewMode='pending',calls=[],renders=0,stales=0;
w.setTimeout=(fn,delay)=>{timers.set(++next,{at:clock+delay,fn});return next;};w.clearTimeout=id=>timers.delete(id);
function advance(ms){clock+=ms;for(const[id,t]of [...timers])if(t.at<=clock){timers.delete(id);t.fn();}}
const status={ok:true,selected:key,repeaters:[{public_key:key,name:'Selected'}],observation_count:2292,last_recorded_at:123,health:{running:true,connected:true,dropped:0,invalid:0,error:'',repeater_error:''}};
const response=(value,code=200)=>({ok:code===200,status:code,json:async()=>value});
function delayed(signal,save){return new Promise((resolve,reject)=>{save(resolve);signal.addEventListener('abort',()=>reject(new w.DOMException('Aborted','AbortError')),{once:true});});}
w.fetch=async(url,options)=>{calls.push({url,signal:options.signal,at:clock});
 if(url.includes('/status')){if(calls.length===1)return delayed(options.signal,r=>pendingStatus=r);return response(status);}
 if(viewMode==='server')return response({ok:false,error_code:'QUERY_TIMEOUT',error:'Query limit reached during neighbors.'},504);
 if(viewMode==='database')return response({ok:false,error_code:'DATABASE_ERROR',error:'Database unreadable.'},503);
 return delayed(options.signal,r=>pendingView=r);
};
w.MeshcoreStationStatisticsVisuals={render:()=>{renders++;},stale:()=>{stales++;},dispose:()=>{}};
const settle=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
(async()=>{try{
 w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_statistics.js','utf8'));
 $('repeater-statistics-disclosure').open=true;await settle();advance(3000);pendingStatus(response(status));await settle();
 assert($('statistics-status').textContent.includes('2292 saved observations'),'status is shown before view response');
 assert.equal($('statistics-view-status').getAttribute('aria-busy'),'true');
 const viewRequest=calls.at(-1);advance(8000);await settle();assert(!viewRequest.signal.aborted,'view gets a fresh 10 seconds after 3-second status request');
 pendingView(response({ok:true,selected:key}));await settle();assert.equal(renders,1);assert.equal($('statistics-view-status').getAttribute('aria-busy'),'false');
 $('statistics-refresh').click();await settle();advance(10001);await settle();
 assert($('statistics-view-error').textContent.includes('browser (10 seconds)'));assert($('statistics-status').textContent.includes('2292 saved observations'));assert.equal(renders,1);
 viewMode='server';$('statistics-refresh').click();await settle();assert($('statistics-view-error').textContent.startsWith('Server query timeout:'));
 viewMode='database';$('statistics-refresh').click();await settle();assert($('statistics-view-error').textContent.startsWith('Database error:'));
 assert(stales>=4,'old snapshots are marked stale before refresh');
 viewMode='pending';$('statistics-refresh').click();await settle();$('repeater-statistics-disclosure').open=false;await settle();assert(calls.at(-1).signal.aborted);advance(60000);await settle();assert.equal(renders,1);
 console.log('Independent 5s status/10s view budgets, immediate status, browser/server/database errors, stale marking and cancellation passed.');
}finally{dom.window.close();}})().catch(e=>{console.error(e);process.exit(1);});
