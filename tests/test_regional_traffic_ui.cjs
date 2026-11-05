/* Scoped theme styling and regional paired bars; saved data only, no radio/API. */
const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
// Dash loads these relevant assets alphabetically, with zzzzz_v5.css last.
const css=['repeater_statistics.css','style.css','zzzzz_v5.css'].map(file=>fs.readFileSync('meshcorestation/web/assets/'+file,'utf8')).join('\n');
const dom=new JSDOM(`<style>${css}</style><style>svg text {fill:black;}</style><main class="shell"><section class="history"><div class="v5-section-body"><div id="statistics-regions" class="statistics-chart"></div></div></section></main><svg id="unrelated"><text>Other chart</text></svg>`,{runScripts:'outside-only',pretendToBeVisual:true,url:'http://localhost'});
const w=dom.window,d=w.document;let requests=0;
w.fetch=()=>{requests++;throw Error('Regional display must not request more data');};
w.eval(fs.readFileSync('meshcorestation/web/assets/statistics_visuals.js','utf8'));
const regions=[{name:'Alpha',receptions:20,unique_packets:5,repeated:15,unidentified:0},{name:'Beta',receptions:12,unique_packets:10,repeated:2,unidentified:0},{name:'Unscoped',receptions:6,unique_packets:4,repeated:2,unidentified:0},{name:'Unknown',receptions:3,unique_packets:0,repeated:2,unidentified:1}];
const data={regions,neighbors:[],selected_repeater:null},saved=JSON.stringify(data);
const bars=()=>[...d.querySelectorAll('.statistics-region-bar')],unique=()=>bars().filter(r=>r.dataset.series==='unique_packets');
const render=()=>w.MeshcoreStationStatisticsVisuals.render(data);
try{
 render();assert(!d.getElementById('statistics-regions-all').checked);
 assert.deepEqual(unique().map(r=>r.dataset.name),['Beta','Alpha','Unscoped','Unknown']);
 assert.equal(bars().length,8);assert(Math.abs(Number(unique()[0].dataset.percentage)-1000/19)<1e-9);
 const dimensions=new Map();
 for(const r of regions){
  const pair=bars().filter(b=>b.dataset.name===r.name),[blue,orange]=pair;
  assert.equal(pair.length,2);assert.equal(blue.getAttribute('fill'),'#2563eb');assert.equal(orange.getAttribute('fill'),'#c75c0d');
  assert.equal(blue.getAttribute('x'),orange.getAttribute('x'));
  assert(Number(blue.getAttribute('y'))+Number(blue.getAttribute('height'))<Number(orange.getAttribute('y')),'upper/lower bars are distinct, not stacked');
  assert(Number(orange.getAttribute('width'))>0,'positive repeats remain visible with the checkbox unchecked');
  assert.equal(Number(blue.dataset.value),r.unique_packets);assert.equal(Number(orange.dataset.value),r.repeated);
  if(r.unique_packets)assert(Math.abs(Number(blue.getAttribute('width'))/r.unique_packets-Number(orange.getAttribute('width'))/r.repeated)<1e-9);
  for(const bar of pair){assert.equal(bar.getAttribute('tabindex'),'0');assert(bar.getAttribute('aria-label').includes(r.receptions+' total observed receptions'));dimensions.set(r.name+'|'+bar.dataset.series,bar.getAttribute('width'));}
 }
 const orange=bars().find(b=>b.dataset.name==='Alpha'&&b.dataset.series==='repeated');
 for(const event of ['pointerenter','focus','click']){orange.dispatchEvent(new w.Event(event));assert(d.querySelector('.statistics-hover-value').textContent.includes('15 repeated receptions'));assert(d.querySelector('.statistics-hover-value').textContent.includes('5 unique messages'));}
 // Theme variables must reach every SVG label, even with extra nested containers
 // and a later generic black-text rule; unrelated visualizations stay unchanged.
 const plot=d.querySelector('.statistics-regional-plot'),nested=d.createElement('section'),svg=plot.querySelector('svg');nested.append(svg);plot.prepend(nested);
 for(const [color,computed]of [['#e6edf7','rgb(230, 237, 247)'],['#1b2938','rgb(27, 41, 56)']]){
  d.documentElement.style.setProperty('--text',color);
  for(const text of d.querySelectorAll('.statistics-regional-plot svg text'))assert.equal(w.getComputedStyle(text).fill,computed);
  assert.equal(w.getComputedStyle(d.querySelector('#unrelated text')).fill,'rgb(0, 0, 0)');
 }
 const checkbox=d.getElementById('statistics-regions-all');checkbox.checked=true;checkbox.dispatchEvent(new w.Event('change'));
 assert.deepEqual(unique().map(r=>r.dataset.name),['Alpha','Beta','Unscoped','Unknown']);
 assert(Math.abs(Number(unique()[0].dataset.percentage)-2000/41)<1e-9);
 assert.equal(bars().length,8);for(const bar of bars())assert.equal(bar.getAttribute('width'),dimensions.get(bar.dataset.name+'|'+bar.dataset.series));
 const details=plot.querySelector('details');details.open=true;details.dispatchEvent(new w.Event('toggle'));assert(details.textContent.includes('Unidentified'));assert(details.textContent.includes('Unknown'));
 checkbox.checked=false;checkbox.dispatchEvent(new w.Event('change'));assert.equal(unique()[0].dataset.name,'Beta');
 for(const days of [1,7,30]){w.MeshcoreStationStatisticsVisuals.render({...data,days,selected:'aa'.repeat(32)});assert(!d.getElementById('statistics-regions-all').checked);assert.equal(bars().length,8);}
 assert.equal(JSON.stringify(data),saved);assert.equal(requests,0);
 w.MeshcoreStationStatisticsVisuals.render({...data,regions:[]});assert(d.getElementById('statistics-regions').textContent.includes('No confidently attributed'));
 console.log('Regional nested SVG light/dark text, paired bars, modes, percentages, exact tooltips, unknown counts, period refresh and no requests passed.');
}finally{dom.window.close();}
