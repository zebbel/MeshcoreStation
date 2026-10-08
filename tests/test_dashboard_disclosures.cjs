const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<html><body><details id="command-history-disclosure"><summary>Command history</summary><div id="command-scroll"><table><tbody id="command-rows"></tbody></table></div></details></body></html>',{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window;
w.requestAnimationFrame=fn=>{fn();return 1};w.cancelAnimationFrame=()=>{};
const section=w.document.getElementById('command-history-disclosure'),box=w.document.getElementById('command-scroll'),body=w.document.getElementById('command-rows');
Object.defineProperty(box,'scrollHeight',{value:800});Object.defineProperty(box,'clientHeight',{value:200});
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
    w.eval(fs.readFileSync('meshcorestation/web/assets/dashboard.js','utf8'));
    body.innerHTML='<tr data-row-id="1"><td>Command</td></tr>';await settle();
    assert(!section.open);assert.equal(box.scrollTop,0);
    section.open=true;section.dispatchEvent(new w.Event('toggle'));await settle();assert.equal(box.scrollTop,800);
    section.open=false;box.scrollTop=50;body.innerHTML='<tr data-row-id="2"><td>New command</td></tr>';await settle();
    assert(!section.open);assert.equal(box.scrollTop,50);
    section.open=true;section.dispatchEvent(new w.Event('toggle'));await settle();assert.equal(box.scrollTop,800);
    dom.window.close();console.log('Collapsed history refresh and reopen scrolling checks passed.');
})().catch(e=>{console.error(e);process.exit(1)});
