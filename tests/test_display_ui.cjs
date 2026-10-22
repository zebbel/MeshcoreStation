const {JSDOM}=require('jsdom'),fs=require('fs'),assert=require('node:assert/strict');
for(const [date_format,hour_format,expected] of [
 ['german','24','22.10.2026 16:30:01'],['iso','24','2026-10-22 16:30:01'],['us','12','10/22/2026 04:30:01 PM']]){
 const dom=new JSDOM('<meta name="meshcorestation-display">',{runScripts:'outside-only'}),w=dom.window;
 w.document.querySelector('meta').content=JSON.stringify({date_format,hour_format,timezone:'Europe/Berlin'});
 w.eval(fs.readFileSync('meshcorestation/web/assets/aa_display.js','utf8'));
 const stamp=Date.parse('2026-10-22T14:30:01Z')/1000;
 assert.equal(w.meshcorestationFormatDate(stamp),expected);
 assert(w.meshcorestationFormatDate(stamp,'UTC').includes(hour_format==='12'?'02:30':'14:30'));
 assert.equal(w.meshcorestationFormatDate(null),'Not recorded');
 const midnight=Date.parse('2026-10-21T22:00:00Z')/1000;
 assert.equal(w.meshcorestationFormatDate(midnight,undefined,{timeOnly:true}),hour_format==='12'?'12:00:00 AM':'00:00:00');
 dom.window.close();
}
console.log('German/ISO/US dates, 12/24-hour clocks, midnight and timezone separation passed.');
