const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM(`<button data-details='{"id":7}'>Details</button><dialog id="details-dialog" open><dl id="detail-fields"></dl></dialog>`,{url:'http://localhost',runScripts:'outside-only'}),w=dom.window;
w.AbortSignal.timeout=()=>undefined;
w.fetch=async(url,options)=>{
 assert.equal(url,'/api/replies/7');assert.equal(options.headers['X-Meshcore-Control'],'1');
 return {ok:true,json:async()=>({window_seconds:300,replies:[
 {message:'<img src=x>',scope:'home',send_status:'accepted',created_at:0,observations:[{seen_at:1,latency:1,rssi:-90,snr:4,route:[{name:'Repeater A',prefix:'aa',status:'forwarding observed'},{name:'bb',prefix:'bb',status:'ambiguous repeater'}]}]},
 {message:'second part',scope:'home',send_status:'uncertain',created_at:0,observations:[],max_attempts:4,retry_status:'forwarding observed',retry_detail:'Receiver delivery remains unconfirmed.',attempts:[
 {attempt:1,timestamp:1000,message:'second part',scope:'home',send_status:'uncertain',created_at:0,observations:[]},
 {attempt:2,timestamp:1001,message:'second part',scope:'home',send_status:'accepted',created_at:2,observations:[]}]}
 ]})};
};
(async()=>{
 w.eval(fs.readFileSync('meshcorestation/web/assets/aa_display.js','utf8'));
w.eval(fs.readFileSync('meshcorestation/web/assets/reply_tracking.js','utf8'));
 w.document.querySelector('button').click();await new Promise(r=>setTimeout(r,30));
 const section=w.document.getElementById('reply-tracking');
 assert(section.textContent.includes('Repeater A [aa] · forwarding observed'));
 assert(section.textContent.includes('ambiguous repeater'));
 assert(section.textContent.includes('Forwarding not confirmed'));
 assert(section.textContent.includes('Send result uncertain'));
 assert.equal(section.querySelectorAll('img').length,0);
 assert(section.textContent.includes('Attempt 2 / 4'));assert(section.textContent.includes('Packet timestamp 1001'));assert(section.textContent.includes('Retry status: forwarding observed'));assert(section.textContent.includes('Receiver delivery is not confirmed'));assert(section.textContent.includes('Accepted by companion'));
 dom.window.close();console.log('Reply details, ambiguous routes, uncertainty and safe text passed.');
})().catch(e=>{console.error(e);dom.window.close();process.exit(1);});
