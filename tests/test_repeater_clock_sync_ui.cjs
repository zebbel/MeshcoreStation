const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const key='ab'.repeat(32),other='cd'.repeat(32);
const dom=new JSDOM(`<details id="repeater-management-disclosure" open><details id="clock-sync-disclosure"><summary><span id="clock-sync-summary"></span></summary><div id="clock-sync-enable-host"></div><select id="clock-sync-interval">${[1,3,6,12,24,48,72,168].map(n=>`<option value="${n}">${n} hours</option>`).join('')}</select><button id="clock-sync-save"></button>${['message','state','attempt','result','success','next','offset','error'].map(s=>`<div id="clock-sync-${s}"></div>`).join('')}</details></details>`,{url:'http://localhost',runScripts:'outside-only'});
const w=dom.window,$=s=>w.document.getElementById('clock-sync-'+s),calls=[];
const defaults=k=>({public_key:k,enabled:0,interval_hours:24,revision:0,last_attempt:null,last_success:null,next_due:null,clock_offset:null,state:'disabled',error:'',uncertain:0});
let db={[key]:defaults(key),[other]:defaults(other)},fail=false,confirmed=0;
w.fetch=async(url,opts={})=>{
    calls.push({url,opts});if(fail)throw Error('Storage unavailable');
    let value;
    if(opts.method==='POST'){const data=JSON.parse(opts.body);assert.equal(opts.headers['X-Meshcore-Control'],'1');value=db[data.public_key]={...db[data.public_key],...data,revision:data.revision+1,state:data.enabled?'scheduled':'disabled',next_due:data.enabled?1800000000:null,uncertain:0};}
    else value=db[new URL(url,'http://localhost').searchParams.get('public_key')];
    return {ok:true,json:async()=>({ok:true,config:value,running:true})};
};
w.confirm=()=>{confirmed++;return true;};
w.eval(fs.readFileSync('meshcorestation/web/assets/aa_display.js','utf8'));
w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_clock_sync.js','utf8'));
const settle=()=>new Promise(r=>setImmediate(r));
const select=k=>w.document.dispatchEvent(new w.CustomEvent('managed-repeater-selected',{detail:k}));
(async()=>{
    assert.equal(calls.length,0);assert.equal($('enabled').checked,false);
    select(key);await settle();assert.equal($('interval').value,'24');assert.equal($('state').textContent,'Disabled');assert.equal($('next').textContent,'Not scheduled');
    $('enabled').checked=true;$('enabled').dispatchEvent(new w.Event('change'));$('interval').value='48';$('interval').dispatchEvent(new w.Event('change'));$('save').click();await settle();
    assert.equal(db[key].enabled,true);assert.equal(db[key].interval_hours,48);assert($('summary').textContent.includes('48 hours'));
    select(other);await settle();assert.equal($('enabled').checked,false);assert.equal($('interval').value,'24');assert.equal(db[key].interval_hours,48);
    db[other]={...db[other],last_attempt:1800000000,last_success:1800000001,clock_offset:-42,error:'Administrator authorization unavailable',state:'error'};
    select(other);await settle();assert.equal($('offset').textContent,'-42.0 seconds');assert($('attempt').textContent.includes('2027'));assert($('error').textContent.includes('Administrator'));
    db[other]={...db[other],enabled:1,uncertain:1,state:'verification_required'};select(other);await settle();assert($('next').textContent.includes('Paused'));
    $('save').click();await settle();assert.equal(confirmed,1);assert.equal(JSON.parse(calls.at(-1).opts.body).acknowledge_uncertain,true);
    fail=true;select(key);await settle();assert.equal($('message').textContent,'Storage unavailable');assert.equal($('save').disabled,true);
    fail=false;select('');await settle();assert.equal($('enabled').checked,false);assert.equal($('save').disabled,true);assert.equal($('summary').textContent,'Select a managed repeater');
    assert(calls.every(c=>c.url.startsWith('/api/repeater-clock-sync')),'Panel never dispatches radio requests');
    const css=fs.readFileSync('meshcorestation/web/assets/repeater_clock_sync.css','utf8');assert(css.includes('var(--text)')&&css.includes('var(--panel)'));assert(css.includes('@media(max-width:600px)'));
    dom.window.close();console.log('Automatic clock settings, status, persistence, switching, pause confirmation and error UI passed.');
})().catch(e=>{console.error(e);dom.window.close();process.exit(1)});
