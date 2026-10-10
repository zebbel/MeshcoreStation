const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM(`<button data-details='{"id":7}'>Details</button><dialog id="details-dialog" open><dl id="detail-fields"></dl></dialog>`,{url:'http://localhost',runScripts:'outside-only'}),w=dom.window;
w.AbortSignal.timeout=()=>undefined;
w.fetch=async(url,options)=>{
 assert.equal(url,'/api/replies/7');assert.equal(options.headers['X-Meshcore-Control'],'1');
 return {ok:true,json:async()=>({window_seconds:300,replies:[
 {message:'<img src=x>',scope:'home',send_status:'accepted',created_at:0,observations:[{seen_at:1,latency:1,rssi:-90,snr:4,route:[{name:'Repeater A',prefix:'aa',status:'forwarding observed'},{name:'bb',prefix:'bb',status:'ambiguous repeater'}]}]},
 {message:'second part',scope:'home',send_status:'uncertain',created_at:0,observations:[]}
 ]})};
};
(async()=>{
 w.eval(fs.readFileSync('meshcorestation/web/assets/reply_tracking.js','utf8'));
 w.document.querySelector('button').click();await new Promise(r=>setTimeout(r,30));
 const section=w.document.getElementById('reply-tracking');
 assert(section.textContent.includes('Repeater A [aa] · forwarding observed'));
 assert(section.textContent.includes('ambiguous repeater'));
 assert(section.textContent.includes('Forwarding not confirmed'));
 assert(section.textContent.includes('Send result uncertain'));
 assert.equal(section.querySelectorAll('img').length,0);
 dom.window.close();console.log('Reply details, ambiguous routes, uncertainty and safe text passed.');
})().catch(e=>{console.error(e);dom.window.close();process.exit(1);});
