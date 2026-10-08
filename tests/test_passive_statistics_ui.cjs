const {JSDOM}=require('jsdom');const fs=require('node:fs');const assert=require('node:assert/strict');
const dom=new JSDOM('<html><body><button id="open-repeater-statistics">Stats</button></body></html>',{runScripts:'outside-only',url:'http://localhost/'});
const w=dom.window;w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'))};w.AbortSignal.timeout=()=>undefined;
w.setInterval=()=>1;w.clearInterval=()=>{};
const key='76'.repeat(32),calls=[];let selected=false;
w.fetch=async(url,opts)=>{calls.push({url,opts});if(opts.method==='POST')selected=true;return {ok:true,json:async()=>({ok:true,selection:selected?{public_key:key,since:100}:null,repeaters:[{public_key:key,name:'My <script>repeater</script>'}],days:1,copies:3,unique:2,repeated:1,ratio:1/3,unidentified:0,ambiguous:1,earliest:100,health:{running:true,heartbeat:200,dropped:2,radio:'Running'},timeline:[{at:100,copies:3,unique:2}],types:{Advertisement:3},roles:{First:2,Middle:1,Final:0},scoped:1,previous:[{key:'aa',name:'Before',status:'unknown',count:2}],following:[],routes:[{path:[{key:'76',name:'My <script>repeater</script>',status:'matched'}],count:3}]})}};
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
    w.eval(fs.readFileSync('meshcorestation/web/assets/aa_dialog.js','utf8'));
    w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_statistics.js','utf8'));
    w.document.getElementById('open-repeater-statistics').click();await settle();
    const d=w.document.getElementById('repeater-statistics-dialog');assert(d.open);assert(d.querySelector('.dialog-body'));assert(d.textContent.includes('Select your repeater'));
    d.querySelector('.stats-repeater').value=key;d.querySelector('.stats-save').click();await settle();
    assert.equal(JSON.parse(calls[1].opts.body).public_key,key);assert(d.textContent.includes('33.3%'));assert(d.textContent.includes('Before'));assert(d.querySelector('svg'));assert(!d.querySelector('script'));
    d.querySelector('.stats-period').value='7';d.querySelector('.stats-period').dispatchEvent(new w.Event('change'));await settle();
    assert(calls.at(-1).url.endsWith('days=7'));assert(calls.every(c=>c.url.startsWith('/api/repeater-statistics')));
    d.querySelector('.stats-close').click();assert(!d.open);
    dom.window.close();console.log('Passive statistics selection, periods, chart and safe rendering checks passed.');
})().catch(e=>{console.error(e);process.exit(1)});
