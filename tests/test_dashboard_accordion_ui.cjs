const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
const main=['bot-disclosure','repeater-management-disclosure','repeater-statistics-disclosure'];
const dom=new JSDOM(main.map(id=>`<details id="${id}"><summary>${id}</summary><input value="retained"></details>`).join('')+['one','two'].map(id=>`<details id="${id}" class="statistics-accordion"><summary>${id}</summary><div>Saved content</div></details>`).join(''),{runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window,d=w.document;let resize=0;w.requestAnimationFrame=fn=>fn();w.MeshcoreStationStatisticsVisuals={resize:()=>resize++};
w.eval(fs.readFileSync('meshcorestation/web/assets/dashboard_accordion.js','utf8'));
function open(id){const el=d.getElementById(id);el.open=true;el.dispatchEvent(new w.Event('toggle'));}
try{
 assert(main.every(id=>!d.getElementById(id).open));open(main[0]);open(main[1]);assert(!d.getElementById(main[0]).open);assert(d.getElementById(main[1]).open);
 open('one');open('two');assert(!d.getElementById('one').open);assert(d.getElementById('two').open);assert(d.getElementById(main[1]).open,'inner accordion is independent');
 open(main[2]);assert(!d.getElementById(main[1]).open);assert(d.getElementById('two').open,'main toggle preserves inner state');
 assert.equal(d.querySelector('#bot-disclosure input').value,'retained');assert.equal(resize,2);
 assert(fs.readFileSync('meshcorestation/web/assets/zzzzz_v5.css','utf8').includes('.shell > .history + .history {margin-top:16px;}'));
 console.log('Independent exclusive accordions, default collapse, state retention, local resize and CSS spacing passed.');
}finally{w.close();}
