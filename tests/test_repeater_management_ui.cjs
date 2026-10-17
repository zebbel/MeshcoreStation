const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('<body></body>',{runScripts:'outside-only'}),w=dom.window;
w.TextEncoder=TextEncoder;
w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
w.HTMLDialogElement.prototype.close=function(){this.open=false;};
w.confirm=()=>true;
const key='ab'.repeat(32),posts=[];let admin=true;
w.fetch=async(url,options)=>{
 const body=JSON.parse(options.body);posts.push(body);
 const result=body.action==='login'?{session:'token',admin,fields:{},contact:{public_key:key}}:
 body.action==='console'?{reply:body.command.startsWith('password')?'Sensitive command response hidden.':'<img src=x onerror=alert(1)>'}:
 {data:{},contact:{public_key:key},sampled_at:1};
 return {ok:true,json:async()=>({ok:true,...result})};
};
w.eval(fs.readFileSync('meshcorestation/web/assets/repeater_management.js','utf8'));
const $=id=>w.document.getElementById(id),settle=()=>new Promise(r=>setImmediate(r));
const submit=id=>$(id).dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
(async()=>{
 w.meshcorestationManageRepeater({public_key:key,name:'Hill',type:2});submit('repeater-login-form');await settle();
 $('repeater-tab-console').click();assert.equal($('repeater-console').hidden,false);assert.equal($('repeater-status').hidden,true);
 $('repeater-console-commands').click();assert.equal($('repeater-command-dialog').open,true);
 const before=posts.length;
 $('repeater-command-search').value='firmware version';$('repeater-command-search').dispatchEvent(new w.Event('input'));
 assert.equal($('repeater-command-list').children.length,1);
 $('repeater-command-list').querySelector('button').click();
 assert.equal($('repeater-console-command').value,'ver');assert.equal(posts.length,before);
 assert.equal($('repeater-command-dialog').open,false);
 $('repeater-console-commands').click();$('repeater-command-search').value='setperm';$('repeater-command-search').dispatchEvent(new w.Event('input'));
 $('repeater-command-list').querySelector('button').click();
 assert.equal($('repeater-console-command').value.slice($('repeater-console-command').selectionStart,$('repeater-console-command').selectionEnd),'<public-key>');
 submit('repeater-console-form');await settle();assert.equal(posts.length,before);
 assert($('repeater-message').textContent.includes('placeholders'));
 $('repeater-console-command').value='get name';submit('repeater-console-form');await settle();
 assert.equal(posts.filter(p=>p.action==='console').length,1);
 assert.equal(posts.at(-1).confirm,true);assert.equal(posts.at(-1).session,'token');
 assert($('repeater-console-log').textContent.includes('<img'));assert.equal($('repeater-console-log').children.length,0);
 $('repeater-console-command').value='password secret';submit('repeater-console-form');await settle();
 assert(!$('repeater-console-log').textContent.includes('password secret'));
 $('repeater-close').click();assert.equal($('repeater-console-log').textContent,'');
 admin=false;w.meshcorestationManageRepeater({public_key:key,name:'Hill',type:2});submit('repeater-login-form');await settle();
 assert.equal($('repeater-console-command').disabled,true);
 $('repeater-tab-console').click();$('repeater-console-command').value='reboot';submit('repeater-console-form');await settle();
 assert.equal(posts.filter(p=>p.action==='console').length,2);
 dom.window.close();console.log('Repeater console tabs, safe output, secret hiding, session cleanup and guest restrictions passed.');
})().catch(e=>{console.error(e);process.exit(1)});
