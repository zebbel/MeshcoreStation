const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
const ids=['status','error','journal','results'];
const dom=new JSDOM(`<details id="repeater-comparison-disclosure"><select id="comparison-repeater"></select><input id="comparison-description"><button id="comparison-save"></button><select id="comparison-change"></select><select id="comparison-period"><option value="1">24h</option><option value="7">7d</option><option value="30">30d</option></select><button id="comparison-run"></button><button id="comparison-refresh"></button><button id="comparison-more"></button>${ids.map(id=>`<div id="comparison-${id}"></div>`).join('')}</details>`,{runScripts:'outside-only',url:'http://localhost',pretendToBeVisual:true}),w=dom.window,d=w.document;
w.AbortSignal.timeout=()=>undefined;w.confirm=()=>true;w.prompt=()=> 'Edited antenna';w.meshcorestationFormatDate=v=>'timestamp '+v;
const A='aa'.repeat(32),B='bb'.repeat(32),calls=[];let description='Antenna',exists=false,measurements={before:{},after:{}};
w.fetch=async(url,options)=>{calls.push({url,options});assert(url.startsWith('/api/repeater-comparison/'));assert.equal(options.headers['X-Meshcore-Control'],'1');
 if(options.method==='POST'){
  const body=JSON.parse(options.body);assert.equal(body.public_key,A);assert(!('timestamp' in body));
  if(body.action==='delete'){assert.equal(body.confirm,true);exists=false;return {ok:true,json:async()=>({ok:true,change:null})};}
  description=body.description;exists=true;return {ok:true,json:async()=>({ok:true,change:{id:1,public_key:A,recorded_at:100,description}})};
 }
 if(url.includes('/changes'))return {ok:true,json:async()=>({ok:true,selected:A,repeaters:[{public_key:A,name:'Managed'}],changes:exists?[{id:1,public_key:A,recorded_at:100,description}]:[],has_more:false})};
 const p={start:0,end:100,future:false,complete:false,coverage_known:false,recorded_seconds:0,expected_seconds:100,snr_samples:2,uncertain_snr_groups:0,notes:[],receptions:null,unique_packets:null,repeated:null,unidentified:null,traffic_per_recorded_hour:null,neighbors:null,one_way:null,two_way:null};
 return {ok:true,json:async()=>({ok:true,selected:A,generated_at:120,change:{id:1,recorded_at:100,description},before:{...p,...measurements.before},after:{...p,start:100,end:200,future:true,...measurements.after},matched:[{public_key:B,name:'Neighbor',before:-12,after:-7,difference_db:5,before_samples:2,after_samples:2}],median_snr_change:5,source_changes:[{public_key:B,name:'Different source',before:1,after:2,before_samples:1,after_samples:10,before_source:'legacy_last_heard',after_source:'firmware_aggregates'}],newly_heard:[],not_heard_after:[],new_observed_neighbors:[],not_observed_after:[],overlapping_changes:[],warnings:['After-period incomplete. Correlation is not causation.'],interpretation:'Preliminary'})};
};
const settle=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));},$=id=>d.getElementById('comparison-'+id);
(async()=>{try{
 w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_comparison.js','utf8'));await settle();assert.equal(calls.length,0,'closed comparison does not request data');
 d.getElementById('repeater-comparison-disclosure').open=true;await settle();assert.equal(calls.length,1);assert($('journal').textContent.includes('No changes'));
 $('description').value='Antenna';$('save').click();await settle();assert(exists);assert.equal($('change').value,'1');assert.equal($('description').value,'');assert(!calls.some(c=>c.url.includes('/view')),'journal changes do not calculate statistics');
 $('run').click();await settle();assert($('results').textContent.includes('+5.00 dB'));assert($('results').textContent.includes('SNR source changed'));assert($('results').textContent.includes('Legacy last-heard estimates'));assert($('results').textContent.includes('Firmware aggregates'));assert($('results').textContent.includes('Incomplete (future)'));assert($('results').textContent.includes('Unavailable'));
 // Percentage changes belong only to Supporting Observations, never SNR.
 measurements={before:{neighbors:10,receptions:4,unique_packets:0,repeated:10,unidentified:3,traffic_per_recorded_hour:.4,one_way:8,two_way:20},after:{neighbors:15,receptions:1,unique_packets:2,repeated:10,unidentified:4,traffic_per_recorded_hour:.3,one_way:12,two_way:0}};
 for(const period of ['1','7','30']){
  $('period').value=period;$('period').dispatchEvent(new w.Event('change'));await settle();
  const support=[...$('results').querySelectorAll('table')].find(t=>t.querySelector('th')?.textContent==='Measurement');
  assert.deepEqual([...support.querySelectorAll('th')].map(n=>n.textContent),['Measurement','Before','After','Difference','Change (%)']);
  const rows=[...support.querySelectorAll('tr')].slice(1).map(r=>[...r.querySelectorAll('td')].map(c=>c.textContent));
  assert.deepEqual(rows.map(r=>r[4]),['+50.0%','−75.0%','N/A','0.0%','+33.3%','−25.0%','+50.0%','−100.0%']);
  assert.deepEqual(rows[0].slice(1,4),['10','15','5']);
  const snr=[...$('results').querySelectorAll('table')].find(t=>t.querySelector('th')?.textContent==='Neighbor');
  assert.deepEqual([...snr.querySelectorAll('th')].map(n=>n.textContent),['Neighbor','Before','After','Change']);
  assert(snr.textContent.includes('+5.00 dB'));assert(!snr.textContent.includes('%'));
 }
 measurements={before:{neighbors:null,receptions:0},after:{neighbors:3,receptions:0}};
 $('period').value='1';$('period').dispatchEvent(new w.Event('change'));await settle();
 const support=[...$('results').querySelectorAll('table')].find(t=>t.querySelector('th')?.textContent==='Measurement');
 const values=[...support.querySelectorAll('tr')].slice(1).map(r=>r.lastChild.textContent);
 assert.equal(values[0],'Unavailable');assert.equal(values[1],'N/A');
 $('period').value='7';$('period').dispatchEvent(new w.Event('change'));await settle();assert(calls.at(-1).url.includes('days=7'));
 [...$('journal').querySelectorAll('button')].find(b=>b.textContent==='Edit').click();await settle();assert.equal(description,'Edited antenna');assert($('journal').textContent.includes('timestamp 100'),'edit preserves original timestamp');
 [...$('journal').querySelectorAll('button')].find(b=>b.textContent==='Delete').click();await settle();assert(!exists);assert($('journal').textContent.includes('No changes'));
 d.getElementById('repeater-comparison-disclosure').open=false;await settle();const count=calls.length;await settle();assert.equal(calls.length,count,'no background comparison polling');
 console.log('Lazy change journal CRUD, protected local API, preserved timestamps, explicit comparisons, periods and incomplete-data labels passed.');
}finally{w.close();}})().catch(e=>{console.error(e);process.exit(1)});
