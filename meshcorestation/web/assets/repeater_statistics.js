(() => {
    let dialog, busy=false, timer=null, requestId=0;
    const el=(tag,value,cls)=>{const node=document.createElement(tag);if(value!=null)node.textContent=value;if(cls)node.className=cls;return node;};
    const date=value=>value ? new Date(value*1000).toLocaleString(undefined,{timeZone:'Europe/Berlin'}) : 'No observations yet';
    function message(value){dialog.querySelector('.stats-message').textContent=value;}
    function table(title,headers,rows){
        const section=el('section',null,'stats-section');section.append(el('h3',title));
        if(!rows.length){section.append(el('p','No matching observations in this period.','muted'));return section;}
        const wrapper=el('div',null,'stats-table-scroll'),table=el('table'),head=el('thead'),tr=el('tr');
        for(const label of headers)tr.append(el('th',label));head.append(tr);table.append(head);
        const body=el('tbody');for(const values of rows){const row=el('tr');for(const value of values)row.append(el('td',value));body.append(row);}table.append(body);wrapper.append(table);section.append(wrapper);return section;
    }
    function chart(points,days){
        const section=el('section',null,'stats-section');section.append(el('h3','Observed traffic over time'));
        section.append(el('p',`${days===1?'Hourly':'24-hour'} buckets · Europe/Berlin labels · blue = RF copies, green = unique payloads per bucket. Unique counts per bucket are not additive across the period.`,'muted'));
        const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 900 210');svg.setAttribute('role','img');svg.setAttribute('aria-label','Observed copies and unique payloads over time');
        const max=Math.max(1,...points.map(p=>p.copies)),width=830/Math.max(1,points.length);
        for(let i=0;i<points.length;i++){
            const p=points[i];for(const [j,key,color] of [[0,'copies','#4d8eff'],[1,'unique','#30b88a']]){
                const bar=document.createElementNS(ns,'rect'),h=150*p[key]/max;
                for(const [attr,value] of Object.entries({x:50+i*width+j*width*.4,y:175-h,width:Math.max(1,width*.35),height:h,fill:color}))bar.setAttribute(attr,value);
                const title=document.createElementNS(ns,'title');title.textContent=`${date(p.at)} · ${key}: ${p[key]}`;bar.append(title);svg.append(bar);
            }
        }
        for(const [x,y,value] of [[4,25,max],[4,178,0],[50,202,date(points[0]?.at)],[600,202,date(points.at(-1)?.at)]]){const label=document.createElementNS(ns,'text');label.setAttribute('x',x);label.setAttribute('y',y);label.textContent=value;svg.append(label);}
        section.append(svg);
        const details=el('details');details.append(el('summary','Show chart values'));details.append(table('Traffic values',['Bucket start','Copies','Unique payloads'],points.map(p=>[date(p.at),p.copies,p.unique])));section.append(details);return section;
    }
    const nodeLabel=n=>`${n.name}${n.status==='matched'?'':` (${n.status})`}`;
    function render(data){
        const select=dialog.querySelector('.stats-repeater');
        select.replaceChildren();const empty=el('option','Not selected / pause collection');empty.value='';select.append(empty);
        for(const repeater of data.repeaters){const option=el('option',`${repeater.name} · ${repeater.public_key.slice(0,12)}`);option.value=repeater.public_key;select.append(option);}
        const selected=data.selection?.public_key || '';
        if(selected && !data.repeaters.some(r=>r.public_key===selected)){const option=el('option',selected+' (no longer in Known repeaters)');option.value=selected;select.append(option);}
        select.value=selected;
        const content=dialog.querySelector('.stats-content');content.replaceChildren();
        if(!selected){content.append(el('p','Select your repeater and choose Save selection to start passive collection. Earlier traffic cannot be reconstructed.'));return;}
        const cards=el('div',null,'stats-metrics');
        for(const [label,value] of [['Observed RF copies',data.copies],['Unique payloads',data.unique],['Repeated copies',data.repeated],['Repeated-copy ratio',data.ratio===null?'—':`${(data.ratio*100).toFixed(1)}%`],['Ambiguous matches',data.ambiguous]]){const card=el('div',null,'stats-metric');card.append(el('p',label,'muted'),el('strong',value));cards.append(card);}content.append(cards);
        content.append(el('p',`Selection active since ${date(data.selection.since)} · Earliest retained observation: ${date(data.earliest)}. Unique/repeated counts use payload fingerprints; ${data.unidentified} copies lack a usable fingerprint and are excluded from those counts.`,'muted'));
        const health=data.health;
        content.append(el('p',`Collector: ${health.running?'running':'not running'} · Radio: ${health.radio || 'unknown'} · Last storage heartbeat: ${date(health.heartbeat)} · Dropped observations: ${health.dropped}${health.trimmed_at ? ` · Storage cap reached at ${date(health.trimmed_at)}; some history was removed.` : ''}${health.error ? ` · Storage error: ${health.error}` : ''}`,'muted'));
        if(!data.copies && !data.ambiguous)content.append(el('p','No matching traffic heard in this period. Collection starts after selection and requires a connected companion. Zero observations do not prove repeater inactivity.'));
        content.append(chart(data.timeline,data.days));
        content.append(table('Packet types',['Type','Observed copies'],Object.entries(data.types)));
        content.append(table('Position within observed routes',['Role','Copies'],Object.entries(data.roles)));
        content.append(el('p',`Roles can overlap, including first and final for a one-repeater path. Scoped flood copies: ${data.scoped}; ordinary flood copies: ${data.copies-data.scoped}.`,'muted'));
        for(const [title,key] of [['Immediately before your repeater','previous'],['Immediately after your repeater','following']])content.append(table(title,['Repeater','Key / prefix','Observed adjacencies'],data[key].map(n=>[nodeLabel(n),n.key,n.count])));
        content.append(table('Most common observed routes',['Repeater sequence','Copies'],data.routes.map(r=>[r.path.map(nodeLabel).join(' → '),r.count])));
        content.append(el('p','Counts include only your selected repeater’s matched flood paths. Ambiguous target prefixes are counted separately and excluded from other totals. Short prefixes can also collide with unknown repeaters. Adjacent hops suggest a directional relationship, not a verified bidirectional link. Direct-route and trace packets are excluded because their paths are not a reliable forwarding history. No message text, raw payloads or network-wide statistics are stored.','muted'));
    }
    async function load(save=false){
        if(busy)return;busy=true;const id=++requestId;
        dialog.querySelectorAll('select,.stats-save,.stats-refresh').forEach(n=>n.disabled=true);message(save?'Saving selection…':'Loading observations…');
        try{
            const url=`/api/repeater-statistics?days=${dialog.querySelector('.stats-period').value}`;
            const response=await fetch(url,{method:save?'POST':'GET',cache:'no-store',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},...(save?{body:JSON.stringify({public_key:dialog.querySelector('.stats-repeater').value})}:{}),signal:AbortSignal.timeout(15000)});
            const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'Statistics request failed.');
            if(id===requestId){render(result);message('Observed by MeshcoreStation · saved metadata only · no radio requests');}
        }catch(error){message(error.message);}finally{busy=false;dialog.querySelectorAll('select,.stats-save,.stats-refresh').forEach(n=>n.disabled=false);}
    }
    function open(){
        if(!dialog){
            dialog=el('dialog');dialog.id='repeater-statistics-dialog';dialog.setAttribute('aria-labelledby','repeater-statistics-title');
            dialog.innerHTML='<div class="dialog-header"><h2 id="repeater-statistics-title">My repeater statistics</h2><button type="button" class="stats-close" aria-label="Close repeater statistics">×</button></div><p class="muted">Passive observations, not the repeater’s total traffic. Only packets heard by this station are available.</p><div class="stats-controls"><label>My repeater<select class="stats-repeater"></select></label><button type="button" class="stats-save">Save selection</button><label>Period<select class="stats-period"><option value="1">24 hours</option><option value="7">7 days</option><option value="30">30 days</option></select></label><button type="button" class="stats-refresh">Refresh</button></div><p class="stats-message" role="status" aria-live="polite"></p><div class="stats-content"></div>';
            window.meshcorestationPrepareDialog(dialog);document.body.append(dialog);
            dialog.querySelector('.stats-close').onclick=()=>dialog.close();
            dialog.querySelector('.stats-save').onclick=()=>load(true);
            dialog.querySelector('.stats-refresh').onclick=()=>load();
            dialog.querySelector('.stats-period').onchange=()=>load();
            // Do not refresh while the user is selecting a different repeater.
            dialog.querySelector('.stats-repeater').onchange=()=>{clearInterval(timer);timer=null;message('Choose Save selection to apply this change.');};
            dialog.addEventListener('close',()=>{clearInterval(timer);timer=null;});
        }
        dialog.showModal();load();clearInterval(timer);timer=setInterval(()=>{if(dialog.open)load();},30000);
        dialog.querySelector('.stats-close').focus();
    }
    document.addEventListener('click',event=>{if(event.target.closest('#open-repeater-statistics'))open();});
})();
