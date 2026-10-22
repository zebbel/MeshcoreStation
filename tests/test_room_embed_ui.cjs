const fs=require('node:fs'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const dom=new JSDOM('<html><body><iframe id="room-server-frame" src="/rooms?embedded=1"></iframe></body></html>',
  {url:'http://localhost/',runScripts:'outside-only'});
const w=dom.window,frame=w.document.getElementById('room-server-frame');
w.eval(fs.readFileSync('meshcorestation/web/assets/aa_display.js','utf8'));
w.eval(fs.readFileSync('meshcorestation/web/assets/room_embed.js','utf8'));
const announce=(origin,height,source=frame.contentWindow)=>w.dispatchEvent(
  new w.MessageEvent('message',{origin,source,data:{kind:'meshcorestation-room-iframe-height',height}})
);
announce('https://evil.example',800);assert.equal(frame.style.height,'');
announce('http://localhost',1044);assert.equal(frame.style.height,'1044px');
announce('http://localhost',Infinity);assert.equal(frame.style.height,'1044px');
announce('http://localhost',1);assert.equal(frame.style.height,'120px');
announce('http://localhost',12000);assert.equal(frame.style.height,'10000px');
announce('http://localhost',999,{other:true});assert.equal(frame.style.height,'10000px');

/* Exercise the actual embedded child resize message with a large document viewport.
   The child should report its own room-shell content, not the inherited frame height. */
(async()=>{
 const child=frame.contentWindow;
 child.document.open();
 child.document.write(fs.readFileSync('meshcorestation/web/rooms.html','utf8'));
 child.document.close();
 let measured=420, resize;
 const shell=child.document.querySelector('.room-shell');
 Object.defineProperty(shell,'scrollHeight',{configurable:true,get:()=>measured});
 shell.getBoundingClientRect=()=>({height:measured});
 Object.defineProperty(child.document.body,'scrollHeight',{configurable:true,get:()=>1900});
 Object.defineProperty(child.document.documentElement,'scrollHeight',{configurable:true,get:()=>1900});
 child.ResizeObserver=class {constructor(fn){resize=fn;}observe(){}};
 child.setInterval=()=>0;
 child.fetch=async()=>({ok:true,json:async()=>({ok:true,rooms:[],status:{running:false,sessions:0,dropped_packets:0}})});
 // jsdom does not load the iframe URL, so its inner location is about:blank.
 // Enable the embedded branch explicitly while retaining the real resize code.
 const original=fs.readFileSync('meshcorestation/web/assets/rooms.js','utf8');
 const childScript=original.replace("if (location.pathname !== '/rooms') return;",'')
   .replace("const embedded = new URLSearchParams(location.search).get('embedded') === '1';","const embedded = true;");
 assert.notEqual(childScript,original);
 const messages=[];
 w.postMessage=(data,targetOrigin)=>{
   messages.push({data,targetOrigin});
   w.dispatchEvent(new w.MessageEvent('message',{origin:w.location.origin,source:child,data}));
 };
 child.eval(childScript);
 await new Promise(resolve=>setTimeout(resolve,15));
 assert(messages.some(item=>item.data.height===428),'The child must post a content-sized height');
 assert.equal(frame.style.height,'428px','Must measure actual child content, not document scroll height');
 measured=735;
 resize();
 await new Promise(resolve=>setTimeout(resolve,15));
 assert.equal(frame.style.height,'743px','Must resize when embedded room contents grow');
 dom.window.close();console.log('Embedded room sizing, content changes and origin checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;dom.window.close();});

