(() => {
    let dialog, busy=false, timer=null, requestId=0, knownRepeaters=[], autoRefreshPaused=false, collectionEnabled=false;
    const el=(tag,value,cls)=>{const node=document.createElement(tag);if(value!=null)node.textContent=value;if(cls)node.className=cls;return node;};
    const date=value=>value ? window.meshcorestationFormatDate(value,'Europe/Berlin') : 'No observations yet';
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
            const p=points[i];for(const [j,key,color] of [[0,'copies','var(--accent)'],[1,'unique','var(--green)']]){
                const bar=document.createElementNS(ns,'rect'),h=150*p[key]/max;
                for(const [attr,value] of Object.entries({x:50+i*width+j*width*.4,y:175-h,width:Math.max(1,width*.35),height:h,fill:color}))bar.setAttribute(attr,value);
                const title=document.createElementNS(ns,'title');title.textContent=`${date(p.at)} · ${key}: ${p[key]}`;bar.append(title);svg.append(bar);
            }
        }
        for(const [x,y,value] of [[4,25,max],[4,178,0],[50,202,date(points[0]?.at)],[600,202,date(points.at(-1)?.at)]]){const label=document.createElementNS(ns,'text');label.setAttribute('x',x);label.setAttribute('y',y);label.textContent=value;svg.append(label);}
        section.append(svg);
        const details=el('details');details.append(el('summary','Show chart values'));details.append(table('Traffic values',['Bucket start','Copies','Unique payloads'],points.map(p=>[date(p.at),p.copies,p.unique])));section.append(details);return section;
    }
    function usefulness(data){
        const u=data.usefulness, panel=el('details',null,'stats-usefulness');
        panel.append(el('summary','Repeater usefulness'),el('p','As observed by this station','muted'));
        if(!u){panel.append(el('p','Summary unavailable.'));return panel;}
        panel.append(el('h3',u.summary));
        const cards=el('div',null,'stats-metrics');
        const replies=u.replies ? `${u.replies.forwarded} / ${u.replies.total}` : 'Unavailable';
        for(const [label,value] of [['Unique packets forwarded',u.unique],['Active hours',`${u.active_hours} / ${u.hours}`],['Different routes',u.routes],['Adjacent repeaters identified',u.neighbors],['Bot replies seen forwarded',replies],['Unique packets vs previous period',u.trend===null?'Not enough comparable data':`${u.trend>0?'+':''}${u.trend}%`]]){
            const card=el('div',null,'stats-metric');card.append(el('strong',value),el('p',label,'muted'));cards.append(card);
        }
        panel.append(cards,el('p',`Observed ${u.unique} unique forwarded packets over ${u.active_hours} hours, with ${u.neighbors} identified adjacent repeaters.`));
        const activity=el('div',null,'stats-activity');
        // One square per hour for 24h; one per day for longer periods.
        const step=data.days===1?1:24;
        for(let i=0;i<u.activity.length;i+=step){const count=u.activity.slice(i,i+step).filter(Boolean).length;
            const square=el('span',null,count?'active':'');square.title=`${data.days===1?'Hour':'Day'} ${i/step+1}: ${count} active hour(s)`;square.setAttribute('aria-label',square.title);activity.append(square);}
        panel.append(el('p',data.days===1?'Hours with observed forwarding':'Days with observed forwarding'),activity);
        if(u.partial)panel.append(el('p','Partial observation history: collection started during this period or records were dropped/trimmed.','muted'));
        panel.append(el('p','Bot replies include completed five-minute observation windows. Activity is based on packets heard, not uptime. Unheard traffic and silent receivers cannot be measured. Trend is unavailable without retained comparison history; 30-day comparisons exceed retention.','muted'));
        return panel;
    }
    const nodeLabel=n=>`${n.name}${n.status==='matched'?'':` (${n.status})`}`;
    function render(data){
        knownRepeaters=data.repeaters;collectionEnabled=!!data.collection_enabled;
        dialog.querySelector('.stats-pause').textContent=collectionEnabled?'Pause collection':'Start collection';
        const select=dialog.querySelector('.stats-repeater');
        select.replaceChildren();const empty=el('option','Not selected / pause collection');empty.value='';select.append(empty);
        for(const repeater of data.repeaters){const option=el('option',`${repeater.name} · ${repeater.public_key.slice(0,12)}`);option.value=repeater.public_key;select.append(option);}
        const selected=data.selection?.public_key || '';
        if(selected && !data.repeaters.some(r=>r.public_key===selected)){const option=el('option',selected+' (no longer in Known repeaters)');option.value=selected;select.append(option);}
        select.value=selected;
        dialog.querySelector('.stats-selected').textContent=selected ? `Selected: ${data.repeaters.find(r=>r.public_key===selected)?.name || selected}` : 'No repeater selected';
        const host=dialog.querySelector('.stats-content');
        const oldDetails=host.querySelector('.stats-detailed'),oldSimple=host.querySelector('.stats-usefulness');
        const detailOpen=oldDetails?.open??false,simpleOpen=oldSimple?.open??false;host.replaceChildren();
        const content=el('details',null,'stats-detailed');content.open=detailOpen;content.append(el('summary','Detailed statistics'));
        const simple=usefulness(data);simple.open=simpleOpen;
        const columns=el('div',null,'stats-columns');columns.append(content,simple);host.append(columns);
        if(!selected){host.replaceChildren(el('p','Choose your repeater on the map to start passive collection. Earlier traffic cannot be reconstructed.'));return;}
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
    function visible(){const section=document.getElementById('repeater-statistics-disclosure');return section?.open && document.getElementById('repeater-optimizer-disclosure')?.open!==false;}
    async function load(save=false){
        if(!visible()){++requestId;return;}
        if(busy&&save)return;
        const id=++requestId;
        await window.meshcorestationEnsureRepeaterSelection?.();
        if(id!==requestId||!visible())return;
        if(window.meshcorestationSelectedRepeater===''){++requestId;dialog.querySelector('.stats-content').replaceChildren();dialog.querySelector('.stats-selected').textContent='No repeater selected';dialog.querySelector('.stats-pause').disabled=true;message('Add a repeater to view its statistics.');return;}
        busy=true;
        dialog.querySelectorAll('select,.stats-save,.stats-refresh,.stats-map,.stats-pause').forEach(n=>n.disabled=true);message(save?'Saving selection…':'Loading observations…');
        try{
            const key=window.meshcorestationSelectedRepeater||'';
            const url=`/api/repeater-statistics?days=${dialog.querySelector('.stats-period').value}`+(key?'&public_key='+encodeURIComponent(key):'');
            const response=await fetch(url,{method:save?'POST':'GET',cache:'no-store',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},...(save?{body:JSON.stringify({public_key:window.meshcorestationSelectedRepeater||dialog.querySelector('.stats-repeater').value,enabled:!collectionEnabled})}:{}),signal:AbortSignal.timeout(60000)});
            const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'Statistics request failed.');
            if(id===requestId){autoRefreshPaused=false;render(result);message('Observed by MeshcoreStation · saved metadata only · no radio requests');}
        }catch(error){if(id!==requestId)return;autoRefreshPaused=true;message(['TimeoutError','AbortError'].includes(error.name)?'Statistics took longer than 60 seconds. Automatic refresh is paused. Try 24 hours or press Refresh to retry.':error.message+' Automatic refresh is paused; press Refresh to retry.');}finally{if(id===requestId){busy=false;dialog.querySelectorAll('select,.stats-save,.stats-refresh,.stats-map,.stats-pause').forEach(n=>n.disabled=false);}}
    }
    function attach(){
        const section=document.getElementById('repeater-statistics-disclosure');
        const host=document.getElementById('repeater-statistics-inline');
        if(!section || !host || dialog)return;
        dialog=host;
        dialog.innerHTML="<p class=\"muted\">Passive observations, not the repeater\u2019s total traffic. Only packets heard by this station are available.</p><div class=\"stats-controls\"><span class=\"stats-selected\">No repeater selected</span><button type=\"button\" class=\"stats-map\">Choose on map</button><button type=\"button\" class=\"stats-pause\">Pause collection</button><select class=\"stats-repeater\" hidden aria-label=\"Selected repeater\"></select><button type=\"button\" class=\"stats-save\" hidden>Save selection</button><label>Period<select class=\"stats-period\"><option value=\"1\">24 hours</option><option value=\"7\">7 days</option><option value=\"30\">30 days</option></select></label><button type=\"button\" class=\"stats-refresh\">Refresh</button></div><p class=\"stats-message\" role=\"status\" aria-live=\"polite\"></p><div class=\"stats-content\"></div>";
        if(document.getElementById('managed-repeater')){dialog.querySelector('.stats-map').hidden=true;}
        document.addEventListener('managed-repeater-selected',()=>{dialog.querySelector('.stats-content').replaceChildren();load();});
        dialog.querySelector('.stats-save').onclick=()=>load(true);
        dialog.querySelector('.stats-map').onclick=()=>document.dispatchEvent(new CustomEvent('stats-picker-open',{detail:{repeaters:knownRepeaters,selected:dialog.querySelector('.stats-repeater').value}}));
        dialog.querySelector('.stats-pause').onclick=()=>load(true);
        document.addEventListener('stats-picker-selected',event=>{
            if(busy || !knownRepeaters.some(r=>r.public_key===event.detail))return;
            dialog.querySelector('.stats-repeater').value=event.detail;load(true);
        });
        dialog.querySelector('.stats-refresh').onclick=()=>load();
        dialog.querySelector('.stats-period').onchange=()=>load();
        function toggle(){
            clearInterval(timer);timer=null;
            if(visible()){
                load();
                timer=setInterval(()=>{if(visible() && !autoRefreshPaused && !document.getElementById('stats-repeater-picker')?.open)load();},30000);
            }
        }
        section.addEventListener('toggle',toggle);
        document.getElementById('repeater-optimizer-disclosure')?.addEventListener('toggle',()=>{if(section.open)toggle();});
        if(section.open)toggle();
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});
    attach();
})();
