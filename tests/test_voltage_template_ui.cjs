const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<button id="open-voltage">Battery</button>',{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window;
w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};w.confirm=()=>true;
w.MeshcoreStationBattery={chart:()=>{},temperatureChart:()=>{},reading:v=>v+' V'};
const key='ab'.repeat(32),calls=[],defaultText='Battery {repeater_name}: {reading} | {sample_time}';
const config={public_key:key,enabled:true,interval_minutes:30,reports_enabled:true,report_time_1:'08:00',report_time_2:'20:00',timezone:'Europe/Berlin',voltage_channel:1,report_target:'bot',report_template:defaultText,revision:1};
w.fetch=async(url,options={})=>{
 const body=options.body?JSON.parse(options.body):null;calls.push({url,body});
 let data={ok:true};
 if(url.includes('/channels'))data.channels=[];
 else if(url==='/api/battery-report-preview')data=body.template.includes('{bad}')?{ok:false,error:'Unknown battery placeholder: {bad}'}:{ok:true,preview:'Hill: 3.86 V'};
 else if(body?.operation==='save'){Object.assign(config,body.value);config.revision++;}
 else data={ok:true,config:{...config},repeaters:[{public_key:key,name:'Hill'}],samples:[],latest:null,rooms:[],reports:[],worker:null,server_time:1,report_default:defaultText,report_placeholders:[{name:'reading',description:'Last reading'}]};
 return {ok:data.ok,json:async()=>data};
};
for(const file of ['aa_dialog','aa_display','voltage'])w.eval(fs.readFileSync('meshcorestation/web/assets/'+file+'.js','utf8'));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 w.document.getElementById('open-voltage').click();await wait(300);
 const field=w.document.getElementById('voltage-template');assert.equal(field.value,defaultText);
 field.value='Report: ';field.focus();field.setSelectionRange(8,8);
 w.document.querySelector('#voltage-placeholders button').click();await wait(300);
 assert.equal(field.value,'Report: {reading}');assert(w.document.getElementById('voltage-template-preview').textContent.includes('3.86'));
 field.value='{bad}';field.dispatchEvent(new w.Event('input',{bubbles:true}));await wait(300);
 assert(w.document.getElementById('voltage-save').disabled);assert(w.document.getElementById('voltage-template-error').textContent.includes('Unknown'));
 field.value='{reading}';field.dispatchEvent(new w.Event('input',{bubbles:true}));await wait(300);
 w.document.getElementById('voltage-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await wait(30);
 const save=calls.find(c=>c.body?.operation==='save');assert.equal(save.body.value.report_template,'{reading}');assert.equal(save.body.value.report_time_1,'08:00');assert.equal(save.body.value.report_target,'bot');assert.equal(save.body.value.temperature_channel,1);
 dom.window.close();console.log('Battery placeholder insertion, live validation/preview and per-repeater save passed.');
})().catch(error=>{console.error(error);dom.window.close();process.exit(1)});
