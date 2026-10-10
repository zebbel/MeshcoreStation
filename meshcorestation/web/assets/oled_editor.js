/* Local draft editor. Only Save persists pages; device previews expire after 30s. */
(() => {
    let dialog, draft, saved, catalog, current=0, selected=-1, timer, sequence=0, busy=false, drag=null, compatible=false;
    const $=id=>document.getElementById(id), clone=v=>JSON.parse(JSON.stringify(v));
    const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
    const btn=(text,fn)=>{const b=el('button',text);b.type='button';b.onclick=fn;return b;};
    const page=()=>draft[current], item=()=>page().elements[selected];
    function message(s){$('oled-message').textContent=s;}
    async function request(body){
        const ctl=new AbortController(), timeout=setTimeout(()=>ctl.abort(),15000);
        try {
            const r=await fetch('/api/oled/pages',{method:body?'POST':'GET',cache:'no-store',signal:ctl.signal,
                headers:{'X-Meshcore-Control':'1',...(body?{'Content-Type':'application/json'}:{})},
                ...(body?{body:JSON.stringify(body)}:{})});
            const data=await r.json();if(!r.ok||!data.ok)throw new Error(data.error||'OLED request failed.');return data;
        } finally {clearTimeout(timeout);}
    }
    function dirty(){return saved&&JSON.stringify(draft)!==JSON.stringify(saved.pages);}
    function state(){ $('oled-dirty').textContent=dirty()?'Unsaved changes':'Saved';$('oled-fields').disabled=busy||!saved||!compatible; }
    function changed(){state();paintBoxes();clearTimeout(timer);const id=++sequence;timer=setTimeout(()=>preview(false,id),350);}
    async function preview(device=false,id=++sequence){
        if(!draft)return;
        try {
            const result=await request({action:device?'device_preview':'preview',pages:clone(draft),page:current});
            if(id!==sequence)return;
            draw(result.drawing);
            message(device?'Companion preview requested for 30 seconds; appears within 10 seconds.':'Live database preview. Text is shortened to its box; firmware fonts may look slightly different.');
        } catch(e){if(id===sequence){$('oled-pixels').replaceChildren();message(e.message);}}
    }
    function draw(drawing){
        const svg=$('oled-pixels');svg.replaceChildren();
        const ns='http://www.w3.org/2000/svg';
        for(const [x1,y1,x2,y2] of drawing.lines){
            const n=document.createElementNS(ns,'line');
            for(const [k,v] of Object.entries({x1,y1,x2,y2,stroke:'white','stroke-width':1}))n.setAttribute(k,v);
            svg.append(n);
        }
        for(const [x,y,size,text] of drawing.texts){
            const n=document.createElementNS(ns,'text');
            for(const [k,v] of Object.entries({x,y:y+7*size,fill:'white','font-family':'monospace','font-size':8*size,textLength:text.length*6*size,lengthAdjust:'spacingAndGlyphs'}))n.setAttribute(k,v);
            n.textContent=text;svg.append(n);
        }
    }
    function paintBoxes(){
        const root=$('oled-boxes');root.replaceChildren();
        page().elements.forEach((e,i)=>{
            const n=el('div');n.className='oled-box'+(selected===i?' selected':'');
            Object.assign(n.style,{left:e.x/128*100+'%',top:e.y/64*100+'%',width:e.w/128*100+'%',height:e.h/64*100+'%'});
            n.tabIndex=0;n.setAttribute('role','button');n.setAttribute('aria-label',(e.kind==='text'?e.text:e.source)+'; drag to move');
            n.onpointerdown=ev=>{
                if(busy)return;ev.preventDefault();selected=i;properties();
                drag={x:ev.clientX,y:ev.clientY,start:clone(e),resize:ev.target.classList.contains('oled-handle')};
                paintBoxes();
            };
            n.onkeydown=ev=>{
                if(ev.key==='Enter'){selected=i;properties();paintBoxes();}
                if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(ev.key)){
                    ev.preventDefault();selected=i;const step=ev.shiftKey?8:1;
                    e.x=Math.max(0,Math.min(128-e.w,e.x+(ev.key==='ArrowRight'?step:ev.key==='ArrowLeft'?-step:0)));
                    e.y=Math.max(0,Math.min(64-e.h,e.y+(ev.key==='ArrowDown'?step:ev.key==='ArrowUp'?-step:0)));
                    properties();changed();$('oled-boxes').children[selected]?.focus();
                }
            };
            if(i===selected){const h=el('span');h.className='oled-handle';h.title='Drag to resize';n.append(h);}
            root.append(n);
        });
    }
    document.addEventListener('pointermove',ev=>{
        if(!drag)return;const r=$('oled-canvas').getBoundingClientRect(),e=item(),s=drag.start;
        const dx=Math.round((ev.clientX-drag.x)/r.width*128),dy=Math.round((ev.clientY-drag.y)/r.height*64);
        if(drag.resize){
            e.w=Math.max(e.kind==='graph'?8:6*e.size,Math.min(128-e.x,s.w+dx));
            e.h=Math.max(e.kind==='graph'?8:8*e.size,Math.min(64-e.y,s.h+dy));
        } else {e.x=Math.max(0,Math.min(128-e.w,s.x+dx));e.y=Math.max(0,Math.min(64-e.h,s.y+dy));}
        properties();changed();
    });
    for(const event of ['pointerup','pointercancel'])document.addEventListener(event,()=>{drag=null;});
    function field(root,title,key,type='text',options=null){
        const label=el('label',title),input=el(options?'select':'input');
        if(options)for(const [value,name] of Object.entries(options)){const o=el('option',name);o.value=value;input.append(o);}
        else {input.type=type;if(type==='number')input.step=['minimum','maximum'].includes(key)?'any':'1';}
        input.value=item()[key]??'';input.setAttribute('aria-label',title);
        input.onchange=()=>{
            item()[key]=(type==='number'||key==='size')?Number(input.value):input.value;
            if(key==='size'){
                const e=item();e.w=Math.max(e.w,6*e.size);e.h=Math.max(e.h,8*e.size);
                e.x=Math.min(e.x,128-e.w);e.y=Math.min(e.y,64-e.h);properties();
            }
            changed();
        };
        label.append(input);root.append(label);
    }
    function properties(){
        const root=$('oled-properties');root.replaceChildren();
        if(selected<0||!item()){root.append(el('p','Select an element, or add one.'));return;}
        const e=item();root.append(el('h3','Element: '+e.kind));
        for(const k of ['x','y','w','h'])field(root,{x:'X',y:'Y',w:'Width',h:'Height'}[k],k,'number');
        if(e.kind!=='graph')field(root,'Text size','size','number',{'1':'Small (6 × 8)','2':'Large (12 × 16)'});
        if(e.kind==='text')field(root,'Text','text');
        else {
            field(root,'Database source','source','text',e.kind==='graph'?catalog.series:catalog.values);
            if(e.kind==='value'){field(root,'Label','label');field(root,'Units','units');field(root,'Decimal places','precision','number');}
            else {field(root,'Time range (hours)','hours','number');field(root,'Minimum','minimum','number');field(root,'Maximum','maximum','number');}
        }
        root.append(btn('Delete element',()=>{page().elements.splice(selected,1);selected=-1;properties();changed();}));
    }
    function render(){
        const list=$('oled-pages');list.replaceChildren();
        draft.forEach((p,i)=>{
            const b=btn((p.enabled?'':'○ ')+p.name,()=>{current=i;selected=-1;render();});
            b.className=current===i?'selected':'';list.append(b);
        });
        $('oled-name').value=page().name;$('oled-enabled').checked=page().enabled;
        properties();paintBoxes();state();clearTimeout(timer);preview();
    }
    function add(kind){
        if(page().elements.length>=16){message('Maximum 16 elements per page.');return;}
        const e={kind,x:0,y:16,w:kind==='graph'?100:96,h:kind==='graph'?40:8};
        if(kind==='text')Object.assign(e,{text:'Your text',size:1});
        if(kind==='value')Object.assign(e,{source:'battery.voltage',size:1,label:'',units:'V',precision:2});
        if(kind==='graph')Object.assign(e,{source:'battery.voltage',hours:24,minimum:3,maximum:4.2});
        page().elements.push(e);selected=page().elements.length-1;properties();changed();
    }
    async function load(){
        if(busy||(dirty()&&!confirm('Discard unsaved OLED edits?')))return;
        busy=true;state();message('Loading pages…');
        try {saved=await request();catalog=saved;draft=clone(saved.pages);current=0;selected=-1;render();}
        catch(e){message(e.message);}finally{busy=false;state();}
    }
    async function save(){
        if(busy)return;busy=true;state();message('Saving…');clearTimeout(timer);++sequence;
        try{saved={...catalog,...await request({action:'save',pages:clone(draft),revision:saved.revision})};draft=clone(saved.pages);message('Saved. Pages update on the companion within 10 seconds.');}
        catch(e){message(e.message);}finally{busy=false;state();}
    }
    function close(){
        if(busy||(dirty()&&!confirm('Discard unsaved OLED edits?')))return;
        ++sequence;clearTimeout(timer);drag=null;dialog.close();if(saved)draft=clone(saved.pages);
        request({action:'stop_preview'}).catch(()=>{});
    }
    function create(){
        dialog=el('dialog');dialog.id='oled-editor';
        dialog.innerHTML='<div class="dialog-header"><h2>OLED screen editor</h2><button type="button" id="oled-close" aria-label="Close editor">×</button></div><p>128 × 64 pixels · Drag elements to move. Drag the blue corner to resize. Arrow keys move selected elements.</p><p id="oled-message" role="status"></p><fieldset id="oled-fields"><div class="oled-toolbar" id="oled-actions"></div><div class="oled-workspace"><aside><h3>Pages</h3><div id="oled-pages"></div><div id="oled-page-actions"></div><label>Page name<input id="oled-name" maxlength="40"></label><label><input id="oled-enabled" type="checkbox"> Enabled</label></aside><section><div class="oled-toolbar" id="oled-add"></div><div id="oled-canvas"><svg id="oled-pixels" viewBox="0 0 128 64" aria-label="Live OLED preview"></svg><div id="oled-boxes"></div></div><p>Database values use the selected battery repeater/channel or received command history. Missing values show --. Graph values outside min/max are clipped.</p><p>Small/large text follows the firmware font sizes. Graphs need graphics-enabled firmware. Page cycling needs button-enabled firmware.</p></section><aside id="oled-properties"></aside></div></fieldset><p id="oled-dirty"></p>';
        document.body.append(dialog);
        $('oled-close').onclick=close;dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
        $('oled-actions').append(btn('Reload',load),btn('Save pages',save),btn('Preview on companion (30s)',()=>preview(true)),btn('Stop companion preview',async()=>{try{await request({action:'stop_preview'});message('Preview stopped; saved pages return within 10 seconds.');}catch(e){message(e.message);}}));
        $('oled-add').append(btn('+ Text',()=>add('text')),btn('+ Database value',()=>add('value')),btn('+ Graph',()=>add('graph')));
        const append=p=>{if(draft.length>=12){message('Maximum 12 pages.');return;}draft.push(p);current=draft.length-1;selected=-1;render();};
        $('oled-page-actions').append(
            btn('Add page',()=>append({name:'New page',enabled:true,elements:[]})),
            btn('Duplicate',()=>append({...clone(page()),name:page().name.slice(0,33)+' copy'})),
            btn('Move up',()=>{if(current>0){[draft[current-1],draft[current]]=[draft[current],draft[current-1]];current--;render();}}),
            btn('Move down',()=>{if(current<draft.length-1){[draft[current+1],draft[current]]=[draft[current],draft[current+1]];current++;render();}}),
            btn('Delete page',()=>{if(draft.length>1&&confirm('Delete this page from the draft?')){draft.splice(current,1);current=Math.min(current,draft.length-1);selected=-1;render();}}));
        $('oled-name').onchange=e=>{page().name=e.target.value;render();};
        $('oled-enabled').onchange=e=>{page().enabled=e.target.checked;changed();};
    }
    function attach(){
        const grid=document.querySelector('#companion-dialog .companion-grid');
        if(!grid||$('oled-settings'))return;
        const section=el('section');section.id='oled-settings';section.className='companion-section';
        section.append(el('h3','OLED pages'),el('p','Design custom companion screens using stored station data.'),btn('Open screen editor',async()=>{
            if(!dialog)create();dialog.showModal();
            if(!draft){draft=[{name:'Loading',enabled:true,elements:[]}];}
            await load();
        }));grid.append(section);section.querySelector('button').disabled=true;availability();
    }
    async function availability(){
        const section=$('oled-settings');if(!section)return;
        try{
            const r=await fetch('/api/oled/pages?status=1',{cache:'no-store',headers:{'X-Meshcore-Control':'1'}});
            const data=await r.json();compatible=Boolean(r.ok&&data.compatible);
            section.querySelector('button').disabled=!compatible;
            section.querySelector('p').textContent=compatible?'Design custom companion screens using stored station data.':(data.reason||'Companion OLED unavailable.');
        }catch(_){compatible=false;section.querySelector('button').disabled=true;}
        if(dialog?.open){state();if(!compatible)message('Companion OLED unavailable. Your unsaved draft is retained.');}
    }
    setInterval(availability,5000);
    window.addEventListener('beforeunload' ,e=>{if(dialog?.open&&dirty()){e.preventDefault();e.returnValue='';}});
    setInterval(()=>{if(dialog?.open&&saved&&!busy&&!drag)preview();},10000);
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
