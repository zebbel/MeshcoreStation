const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const A='aa'.repeat(32),B='bb'.repeat(32);
const dom=new JSDOM(`<details id="repeater-statistics-disclosure" open><select id="statistics-repeater"><option value="${A}">A</option><option value="${B}">B</option></select><button id="statistics-refresh"></button><fieldset><input id="neighbor-monitor-enabled" type="checkbox"><input id="neighbor-monitor-interval" value="47"><button id="neighbor-monitor-read-now" disabled>Read now</button><p id="neighbor-monitor-read-status"></p></fieldset></details>`,{url:'http://localhost',runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window,d=w.document,$=id=>d.getElementById(id),timers=new Map(),calls=[];
let job=null,busy=false,posts=0,refreshes=0,fail=false,ready=true,identifier=0;
const nativeTimeout=w.setTimeout.bind(w),nativeClear=w.clearTimeout.bind(w);
w.setTimeout=(fn,delay)=>{if(delay===1500){const id=10000+(++identifier);timers.set(id,fn);return id;}return nativeTimeout(fn,delay);};
w.clearTimeout=id=>{if(timers.has(id))timers.delete(id);else nativeClear(id);};
$('statistics-refresh').onclick=()=>refreshes++;
w.fetch=async(url,options)=>{
    calls.push({url,options});assert(url.startsWith('/api/repeater-statistics/read-now'));assert.equal(options.headers['X-Meshcore-Control'],'1');
    if(fail)throw Error('Status unavailable');
    if(options.method==='POST'){
        posts++;const body=JSON.parse(options.body);assert.deepEqual(Object.keys(body),['public_key']);assert.equal(body.public_key,$('statistics-repeater').value);
        job={job_id:'one',public_key:body.public_key,state:'queued',records:0,progress:'Queued for radio',error:''};busy=true;
        return {ok:true,status:202,json:async()=>({ok:true,job:{...job},busy,ready})};
    }
    return {ok:true,status:200,json:async()=>({ok:true,job:job?{...job}:null,busy,ready})};
};
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));};
const poll=async()=>{const next=timers.entries().next().value;assert(next,'expected a local status poll');timers.delete(next[0]);next[1]();await settle();};
(async()=>{try{
    w.eval(fs.readFileSync('meshcorestation/web/assets/neighbor_snr_read_now.js','utf8'));
    const control=w.MeshcoreStationNeighborReadNow;
    control.load(A);await settle();assert(!$('neighbor-monitor-read-now').disabled);assert(!$('neighbor-monitor-enabled').checked);
    $('neighbor-monitor-read-now').click();assert($('neighbor-monitor-read-now').disabled);assert($('neighbor-monitor-read-status').textContent.includes('Reading neighbor SNR…'));await settle();
    assert.equal(posts,1);assert($('neighbor-monitor-read-now').disabled);$('neighbor-monitor-read-now').click();assert.equal(posts,1);
    job={...job,state:'running',records:2,progress:'Received 2 completed aggregate records'};await poll();
    assert($('neighbor-monitor-read-status').textContent.includes('Records retrieved: 2'));
    assert.equal($('neighbor-monitor-interval').value,'47');assert(!$('neighbor-monitor-enabled').checked);
    fail=true;await poll();assert($('neighbor-monitor-read-now').disabled,'A status error must not enable duplicate submission while the known job runs');fail=false;
    job={...job,state:'complete',records:3};busy=false;await poll();
    assert.equal(refreshes,1);assert(!$('neighbor-monitor-read-now').disabled);assert($('neighbor-monitor-read-status').textContent.includes('Read complete'));
    control.load(A);await settle();assert.equal(refreshes,1,'Reopening must not refresh an old result a second time');
    job={...job,job_id:'two',state:'running',records:1};busy=true;control.load(A);await settle();
    $('repeater-statistics-disclosure').open=false;control.stop();assert.equal(timers.size,0);assert.equal(job.state,'running','Closing UI does not cancel server work');
    job={...job,state:'partial',records:4,error:'Cycle budget reached'};busy=false;
    $('repeater-statistics-disclosure').open=true;control.load(A);await settle();assert($('neighbor-monitor-read-status').textContent.includes('Partial read'));assert.equal(refreshes,1,'Normal reopen already loads the saved view');
    $('statistics-repeater').value=B;job=null;control.load(B);await settle();assert(!$('neighbor-monitor-read-now').disabled);
    ready=false;control.load(B);await settle();assert($('neighbor-monitor-read-now').disabled);assert($('neighbor-monitor-read-status').textContent.includes('disconnected'));
    assert(calls.every(c=>c.url.startsWith('/api/repeater-statistics/read-now')),'Only explicit POST queues a read; GET polls are local');
    assert.equal(posts,1);assert(!$('neighbor-monitor-enabled').checked);assert.equal($('neighbor-monitor-interval').value,'47');
    const css=fs.readFileSync('meshcorestation/web/assets/repeater_statistics.css','utf8');assert(css.includes('#neighbor-monitor-read-status'));assert(css.includes('overflow-wrap:anywhere'));
    console.log('Manual SNR read: disabled-auto support, progress, duplicate prevention, saved refresh, errors, selection and collapse behavior passed.');
}finally{dom.window.close();}})().catch(e=>{console.error(e);process.exit(1)});
