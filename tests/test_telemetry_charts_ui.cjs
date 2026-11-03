const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<div id="voltage"></div><p id="vn"></p><div id="temp"></div><p id="tn"></p>',{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window,d=w.document;
for(const file of ['aa_display','ab_battery'])w.eval(fs.readFileSync('meshcorestation/web/assets/'+file+'.js','utf8'));
const charts=w.MeshcoreStationBattery,end=1700000000;
const samples=[{sampled_at:end-3600,voltage:3.92,temperature:24.6,interval_seconds:1800},
 {sampled_at:end-1800,voltage:4.01,temperature:0,interval_seconds:1800},
 {sampled_at:end-900,voltage:3.7,temperature:-5.4,interval_seconds:1800},
 {sampled_at:end-400,voltage:null,temperature:null,interval_seconds:1800}];
function draw(field,days=1,points=samples){
 const box=d.getElementById(field==='voltage'?'voltage':'temp'),note=d.getElementById(field==='voltage'?'vn':'tn');
 (field==='voltage'?charts.chart:charts.temperatureChart)(box,note,points,'Europe/Berlin',days,end);
 const svg=box.querySelector('svg');if(svg)svg.getBoundingClientRect=()=>({left:10,top:20,width:470,height:145});
 return {box,svg};
}
function coordinates(field,index,points=samples){const p=points[index],x=70+(p.sampled_at-(end-86400))/86400*846;let low=3,high=4.2;if(field==='temperature'){const values=points.map(p=>p.temperature).filter(Number.isFinite),padding=Math.max(1,(Math.max(...values)-Math.min(...values))*.1);low=Math.floor(Math.min(...values)-padding);high=Math.ceil(Math.max(...values)+padding);}const y=20+(high-(field==='voltage'?p.voltage:p.temperature))/(high-low)*222;return {clientX:10+x/2,clientY:20+y/2};}
for(const field of ['voltage','temperature']){
 let {svg}=draw(field);const dots=[0,1,2];
 assert.equal(svg.querySelectorAll('circle').length,0,'clean line has no permanent markers');assert.equal(svg.querySelectorAll('title').length,0,'No hover popup or timestamp');
 svg.dispatchEvent(new w.MouseEvent('click',{bubbles:true,...coordinates(field,0)}));
 assert.equal(svg.querySelector('.telemetry-selected-value').textContent,field==='voltage'?'3.92 V':'24.6 °C');
 assert(d.getElementById(field==='voltage'?'vn':'tn').textContent.includes('2023'),'selected measurement includes its timestamp');
 const touch=new w.Event('touchstart',{bubbles:true});Object.defineProperty(touch,'touches',{value:[coordinates(field,1)]});svg.dispatchEvent(touch);
 assert.equal(svg.querySelector('.telemetry-selected-value').textContent,field==='voltage'?'4.01 V':'0.0 °C');
 svg.dispatchEvent(new w.MouseEvent('pointerdown',{bubbles:true,...coordinates(field,2)}));
 assert.equal(svg.querySelector('.telemetry-selected-value').textContent,field==='voltage'?'3.70 V':'-5.4 °C');
 assert.equal(svg.querySelectorAll('.telemetry-selected-value').length,1);
 const renewed=draw(field).svg;
 assert.equal(renewed.querySelector('.telemetry-selected-value').textContent,field==='voltage'?'3.70 V':'-5.4 °C','Background refresh preserves selection');
 assert(!renewed.querySelector('foreignObject'));
}
const history=[...samples,{sampled_at:end-2*86400,voltage:3.5,temperature:10},{sampled_at:end-8*86400,voltage:3.6,temperature:12}];
for(const field of ['voltage','temperature'])for(const [days,count] of [[1,3],[7,4],[30,5]]){
 const {svg}=draw(field,days,history);assert.equal(svg.querySelectorAll('circle.voltage-dot,circle.voltage-outside').length,0);assert(svg.querySelector('path.voltage-line'));
}
// Values need not have a rendered dot to remain selectable in a dense history.
const dense=Array.from({length:2000},(_,i)=>({sampled_at:end-2000+i,voltage:3.92,temperature:24.6,interval_seconds:1}));
for(const field of ['voltage','temperature']){
 const {svg}=draw(field,1,dense);assert(svg.querySelectorAll('.voltage-dot').length<601);
 const x=70+(dense[1].sampled_at-(end-86400))/86400*(940-70-24),y=field==='voltage'?20+(4.2-3.92)/1.2*222:131;
 svg.dispatchEvent(new w.MouseEvent('click',{clientX:10+x/2,clientY:20+y/2}));
 assert(Math.abs(Number(svg.querySelector('.telemetry-selected-point').getAttribute('cx'))-x)<1e-9);
}
for(const field of ['voltage','temperature']){const {svg}=draw(field);svg.dispatchEvent(new w.MouseEvent('pointermove',coordinates(field,0)));assert(svg.querySelector('.telemetry-selected-point'));svg.dispatchEvent(new w.Event('pointerleave'));assert(!svg.querySelector('.telemetry-selected-point'));svg.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowLeft'}));assert(svg.querySelector('.telemetry-selected-point'));svg.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape'}));assert(!svg.querySelector('.telemetry-selected-point'));}
const empty=draw('temperature',1,samples.map(p=>({...p,temperature:null})));assert(!empty.svg);assert(empty.box.textContent.includes('No temperature readings'));
dom.window.close();console.log('Voltage/temperature charts: mouse/touch selection, value-only labels, refresh, zero/negative values, history periods and dense histories passed.');
