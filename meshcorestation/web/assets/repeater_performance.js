/* Local saved observations and annotations only. No interval, radio or Analyzer fetch. */
(() => {
    const $=id=>document.getElementById(id), names=()=>window.MeshcoreStationRepeaterNames;
    const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=String(text);if(cls)e.className=cls;return e;};
    const fmt=n=>n==null?'Not available':Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
    const date=t=>t==null?'Not recorded':window.meshcorestationFormatDate(t);
    const visible=()=>$('repeater-performance-disclosure')?.open&&$('repeater-optimizer-disclosure')?.open;
    const drafts=new Map();let attached=false,controller=null,writer=null,generation=0,key='',selectedMarker=null,comparisonDays=7,lastData=null,lastWidth=0;
    const labels={companion_packets:'Companion path packets',distinct_packets:'Distinct observed packet IDs',observed_routes:'Observed route patterns',companion_network_packets:'All Companion network packets',analyzer_hourly_relays_mean:'Mean analyzer rolling 1h relays',analyzer_neighbors_mean:'Mean observed neighboring repeaters',analyzer_bidirectional_mean:'Mean confirmed bidirectional relationships',optimizer_neighbors_mean:'Mean optimizer neighbor records'};
    function stop(){++generation;controller?.abort();controller=null;writer?.abort();writer=null;}
    function table(headers,rows){const wrap=node('div',null,'stats-table-scroll'),table=node('table'),head=node('tr');headers.forEach(h=>head.append(node('th',h)));const thead=node('thead');thead.append(head);table.append(thead);const body=node('tbody');for(const cells of rows){const tr=node('tr');for(const v of cells){const td=node('td');td.append(v instanceof Node?v:document.createTextNode(String(v)));tr.append(td);}body.append(tr);}table.append(body);wrap.append(table);return wrap;}
    function compare(id){selectedMarker=id;load(true);}
    function chart(title,data,series){
        const box=node('section',null,'stats-section');box.append(node('h3',title));
        const legend=node('div',null,'stats-controls muted');for(const [,label,color] of series){const item=node('span',null,'performance-series'),line=node('span',null,'performance-swatch');line.style.borderTopColor=color;line.setAttribute('aria-hidden','true');item.append(line,document.createTextNode(label));legend.append(item);}box.append(legend,node('p','Blank intervals mean no saved observations. Vertical lines mark logged changes.','muted'));
        const width=Math.max(320,Math.min(900,$('performance-content').clientWidth||900)),plot=width-70;
        box.classList.add('performance-chart-section');
        if(!data.timeline.some(p=>series.some(s=>p[s[0]]!=null)))box.append(node('p','No saved observations for this chart in the selected window. This does not mean zero activity.','stats-message'));
        const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('class','stats-chart performance-chart');svg.setAttribute('viewBox',`0 0 ${width} 240`);svg.setAttribute('role','group');svg.setAttribute('aria-label',title);
        const add=(tag,attrs,text)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!=null)e.textContent=text;svg.append(e);return e;};
        const begin=data.start,end=data.now,scale=Math.max(1,...data.timeline.flatMap(p=>series.map(s=>p[s[0]]??0))),x=t=>50+plot*(t-begin)/(end-begin),y=v=>185-155*v/scale;
        add('path',{d:`M50 25V185H${width-20}`,fill:'none',stroke:'var(--border)'});
        const ticks=width<600?2:3;for(let i=0;i<=ticks;i++){const value=scale*i/ticks;add('text',{x:44,y:y(value)+4,'text-anchor':'end'},Number(value).toLocaleString('en-US',{notation:'compact',maximumFractionDigits:1}));const at=begin+(end-begin)*i/ticks;const label=new Intl.DateTimeFormat('en-GB',{timeZone:window.meshcorestationDisplaySettings?.timezone||'Europe/Berlin',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(at*1000));add('text',{x:x(at),y:215,'text-anchor':i===0?'start':i===ticks?'end':'middle'},label);}
        for(const [field,label,color] of series){let path='',active=false;
            for(const p of data.timeline){const v=p[field];if(v==null){active=false;continue;}const bucketed=field==='copies'||field==='network',stamp=bucketed?p.at:field==='optimizer_neighbors'?(p.optimizer_at??p.at):(p.analyzer_at??p.at);const at=Math.max(begin,Math.min(end,bucketed?p.at+data.step/2:stamp));path+=(active?'L':'M')+x(at)+' '+y(v);active=true;const dot=add('circle',{cx:x(at),cy:y(v),r:3,fill:color});const tip=document.createElementNS(ns,'title');tip.textContent=`${date(stamp)} · ${label}: ${fmt(v)}`;dot.append(tip);}
            add('path',{d:path,fill:'none',stroke:color,'stroke-width':2});
        }
        for(const marker of data.markers.filter(m=>m.at>=begin&&m.at<=end)){
            const line=add('rect',{x:x(marker.at)-8,y:18,width:16,height:172,fill:'transparent',class:'performance-change-line',tabindex:0,role:'button','aria-label':marker.description});
            add('path',{d:`M${x(marker.at)} 18V190`,stroke:'var(--accent)','stroke-width':3,'stroke-dasharray':'5 4',class:'performance-marker-line','pointer-events':'none','aria-hidden':'true'});
            const tip=document.createElementNS(ns,'title');tip.textContent=marker.description+' · '+date(marker.at);line.append(tip);line.addEventListener('click',()=>compare(marker.id));line.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();compare(marker.id);}});
        }
        box.append(svg);
        const detail=node('details');detail.append(node('summary','Show measured values'));
        detail.append(table(['Bucket begins',...series.map(s=>s[1])],data.timeline.map(p=>[date(p.at),...series.map(s=>fmt(p[s[0]]))])));box.append(detail);return box;
    }
    function localInput(at){const d=new Date(at*1000);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,19);}
    function editor(host,data){
        const section=node('section',null,'stats-section');section.append(node('h3','Log Change'),node('p','This is a local journal entry. Saving it never sends a command or changes the repeater. Date/time uses this browser’s local timezone. Leave it blank for the current server time.','muted'));
        const form=node('form',null,'performance-form'),description=node('textarea'),time=node('input'),save=node('button','Save marker'),cancel=node('button','Cancel edit');description.rows=2;description.maxLength=500;description.required=true;description.id='performance-description';time.type='datetime-local';time.step='1';time.id='performance-change-time';save.type='submit';cancel.type='button';
        const d=drafts.get(key)||{};description.value=d.description||'';time.value=d.time||'';cancel.hidden=!d.id;
        for(const [title,input] of [['Change description',description],['Date/time (optional)',time]]){const label=node('label',title);label.append(input);form.append(label);}form.append(save,cancel);section.append(form);host.append(section);
        const saveDraft=()=>drafts.set(key,{...d,description:description.value,time:time.value});description.oninput=saveDraft;time.oninput=saveDraft;
        cancel.onclick=()=>{drafts.delete(key);load();};
        form.onsubmit=async e=>{e.preventDefault();if(!form.reportValidity())return;const draft=drafts.get(key)||d,body={action:draft.id?'edit':'create',description:description.value};if(draft.id)body.id=draft.id;if(time.value)body.at=time.value===draft.originalInput?draft.originalAt:new Date(time.value).getTime()/1000;await mutate(body,save,()=>drafts.delete(key));};
    }
    async function mutate(body,button,success){
        if(!visible())return;const target=key,version=generation;button.disabled=true;writer=new AbortController();const write=writer;let timedOut=false;const timeout=setTimeout(()=>{timedOut=true;write.abort();},15000);
        try{const response=await fetch('/api/repeater-performance',{method:'POST',headers:{'Content-Type':'application/json','X-Meshcore-Control':'1'},body:JSON.stringify({...body,public_key:target}),signal:write.signal});const r=await response.json();if(!response.ok||!r.ok)throw Error(r.error||'Could not save the change marker.');if(version!==generation||target!==key||!visible())return;success?.();if(body.action==='delete'&&selectedMarker===body.id)selectedMarker=null;await load();}
        catch(e){if(version===generation&&(e.name!=='AbortError'||timedOut))$('performance-status').textContent='Change marker request failed: '+(timedOut?'request timed out; refresh saved data before retrying.':e.message);}
        finally{clearTimeout(timeout);if(writer===write)writer=null;if(version===generation)button.disabled=false;}
    }
    function journal(host,data){
        const section=node('section',null,'stats-section');section.append(node('h3','Recorded changes'));
        if(!data.markers.length)section.append(node('p','No changes logged for this repeater.'));
        else section.append(table(['When','Change','Source','Actions'],data.markers.map(m=>{
            const buttons=node('div',null,'stats-controls');const open=node('button','Compare'),edit=node('button','Edit'),remove=node('button','Delete');open.onclick=()=>compare(m.id);edit.onclick=()=>{const input=localInput(m.at);drafts.set(key,{id:m.id,description:m.description,time:input,originalInput:input,originalAt:m.at});render(data);$('performance-description').focus();};remove.onclick=()=>{if(window.confirm('Delete this local marker? This does not change the repeater or its configuration audit.'))mutate({action:'delete',id:m.id},remove);};buttons.append(open,edit,remove);
            const source=node('span',m.source_id?'Verified configuration record':'Manual journal entry');if(m.source_id){const details=node('details');details.append(node('summary','Original audit details'),node('p','Recorded at '+date(m.source_at)),node('p',m.provenance));source.append(details);}return [date(m.at),m.description,source,buttons];
        })));host.append(section);
    }
    function comparison(host,data){
        if(!data.comparison)return;const c=data.comparison,section=node('section',null,'stats-section');section.id='performance-comparison';const marker=data.markers.find(m=>m.id===selectedMarker);section.append(node('h3','Before/after: '+(marker?.description||'Recorded change')));
        const label=node('label','Equal observation windows'),select=node('select');for(const [value,text] of [[1,'24 hours before/after'],[3,'3 days before/after'],[7,'7 days before/after']]){const option=node('option',text);option.value=value;select.append(option);}select.value=comparisonDays;select.onchange=()=>{comparisonDays=Number(select.value);load(true);};label.append(select);section.append(label);
        for(const name of ['before','after']){const w=c.windows[name];section.append(node('p',`${name==='before'?'Before':'After'}: ${date(w.start)} → ${date(w.end)}. Analyzer samples: ${w.analyzer_samples}/${w.expected_hourly_samples}. Companion buckets with received packets: ${w.companion_buckets_with_packets}. Optimizer samples: ${w.optimizer_samples}. Elapsed through ${date(w.observed_until)}; Companion first/last: ${date(w.first_companion)} / ${date(w.last_companion)}.`,'muted'));}
        section.append(table(['Measurement','Before','After','Difference','Percent change (observed only)'],Object.keys(labels).filter(field=>c.differences[field]).map(field=>{const v=c.differences[field];return [labels[field],fmt(v.before),fmt(v.after),fmt(v.absolute),v.percent==null?(v.reason||'Not available (missing/zero baseline)'):fmt(v.percent)+'%'];})));
        section.append(node('p',c.interpretation));for(const warning of c.warnings)section.append(node('p',warning,'stats-message'));host.append(section);
    }
    function charts(data){return [chart('Companion observations',data,[['copies','Packets involving this repeater','var(--accent)'],['network','All received network packets','var(--muted)']]),chart('Analyzer forwarding activity — rolling 1h measurements',data,[['relay_1h','Rolling 1h relay count','var(--accent)']]),chart('Analyzer Network Reach',data,[['neighbors','Neighboring repeaters','var(--accent)'],['two_way','Confirmed bidirectional observations','var(--green)'],['optimizer_neighbors','Optimizer neighbor records (reception only)','var(--muted)']])];}
    function render(data){
        lastData=data;names().ingest(data.repeaters||[]);const host=$('performance-content');host.replaceChildren();$('performance-selected').replaceChildren(names().element(key));
        const l=data.local,a=data.analyzer,last=Math.max(l.last||0,a?.at||0,data.optimizer_neighbors?.at||0),recent=last&&data.now-last<=3600;
        const cards=node('div',null,'stats-metrics');
        for(const [title,value,explanation] of [
            ['Mesh Activity',fmt(l.copies)+' observed path packets',`Analyzer: ${fmt(a?.relay_1h)} relays / rolling 1h; ${fmt(a?.relay_24h)} / rolling 24h. Received paths are evidence of involvement, not verified direct forwarding.`],
            ['Network Reach',fmt(a?.neighbors)+' neighboring repeaters',`${fmt(a?.two_way)} confirmed bidirectional observations, retrieved ${date(a?.at)}. Optimizer: ${fmt(data.optimizer_neighbors?.observed)} neighbor records${data.optimizer_neighbors?' at '+date(data.optimizer_neighbors.at):''}. Neighbor reception alone does not prove bidirectional delivery.`],
            ['Mesh Contribution',fmt(l.unique)+' distinct packet IDs',`${fmt(l.routes)} route patterns involving this repeater, from ${fmt(l.network)} Companion network packet copies. Sources are not added together.`],
            ['Data Quality',!last?'No saved observations':recent?'Recent, partial observations':'Older observations',`Latest saved observation: ${date(last||null)}. Saved analyzer intervals: ${data.analyzer_buckets}/${data.timeline.length}. ${fmt(l.ambiguous)} uncertain path observations excluded. Continuous Companion coverage cannot be confirmed. Open Repeater Network Monitoring to collect fresh analyzer measurements.`]
        ]){const card=node('div',null,'stats-metric');card.append(node('p',title,'muted'),node('strong',value),node('p',explanation,'muted'));cards.append(card);}host.append(cards);
        if(l.error)host.append(node('p',l.error,'stats-message'));if(a)host.append(node('p','Latest analyzer retrieval: '+date(a.at)+'. Archive retains up to 400 days within a shared sample limit.','muted'));
        host.append(node('p','Companion source: '+l.source+'. These copies are not added to copies in the other local store.','muted'));
        data.notes.forEach(note=>host.append(node('p',note,'muted')));
        host.append(...charts(data));
        editor(host,data);journal(host,data);comparison(host,data);
    }
    async function load(scroll=false){
        if(!visible())return;await window.meshcorestationEnsureRepeaterSelection?.();if(!visible())return;
        const next=window.meshcorestationSelectedRepeater||'';if(next!==key){key=next;selectedMarker=null;lastData=null;$('performance-content').replaceChildren();}stop();const version=generation;
        if(!key){$('performance-status').textContent='Select a managed repeater in Repeater Management.';$('performance-selected').textContent='No repeater selected';return;}
        $('performance-selected').replaceChildren(names().element(key));controller=new AbortController();const active=controller;let timedOut=false;const timeout=setTimeout(()=>{timedOut=true;active.abort();},15000);$('performance-content').setAttribute('aria-busy','true');$('performance-status').textContent='Loading saved performance observations…';
        try{const response=await fetch(`/api/repeater-performance?public_key=${encodeURIComponent(key)}&days=${$('performance-days').value}${selectedMarker?'&marker_id='+selectedMarker+'&compare_days='+comparisonDays:''}`,{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal:active.signal});const data=await response.json();if(version!==generation||!visible())return;if(!response.ok||!data.ok)throw Error(data.error||'Performance data unavailable.');if(data.public_key!==key||!data.local||!Array.isArray(data.notes)||!Array.isArray(data.timeline)||!Array.isArray(data.markers))throw Error('Invalid performance response.');render(data);$('performance-status').textContent='Saved observations loaded. Gaps are not zero activity. Refresh saved data does not contact the radio or analyzer.';if(scroll)$('performance-comparison')?.scrollIntoView?.({block:'start'});}
        catch(e){if(version===generation&&(e.name!=='AbortError'||timedOut))$('performance-status').textContent='Performance unavailable: '+(timedOut?'request timed out.':e.message)+' Existing displayed observations may be outdated.';}
        finally{clearTimeout(timeout);if(version===generation)$('performance-content')?.setAttribute('aria-busy','false');}
    }
    function attach(){if(attached||!$('performance-content'))return;attached=true;const toggle=()=>{if(visible())load();else{stop();$('performance-content').setAttribute('aria-busy','false');}};$('repeater-performance-disclosure').addEventListener('toggle',toggle);$('repeater-optimizer-disclosure').addEventListener('toggle',toggle);$('performance-days').onchange=()=>load();$('performance-refresh').onclick=()=>load();document.addEventListener('managed-repeater-selected',()=>{stop();key='';selectedMarker=null;lastData=null;$('performance-content').replaceChildren();if(visible())load();});document.addEventListener('repeater-network-updated',e=>{if(visible()&&e.detail===key)load();});if(window.ResizeObserver)new ResizeObserver(()=>{const width=$('performance-content').clientWidth;if(visible()&&lastData?.public_key===key&&width!==lastWidth){lastWidth=width;const old=[...$('performance-content').querySelectorAll('.performance-chart-section')],fresh=charts(lastData);old.forEach((n,i)=>n.replaceWith(fresh[i]));}}).observe($('performance-content'));if(visible())load();}
    new MutationObserver(attach).observe(document.documentElement,{subtree:true,childList:true});attach();
})();
