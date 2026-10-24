/* Local saved observations and annotations only. No interval, radio or Analyzer fetch. */
(() => {
    const $=id=>document.getElementById(id), names=()=>window.MeshcoreStationRepeaterNames;
    const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=String(text);if(cls)e.className=cls;return e;};
    const fmt=n=>n==null?'Not available':Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
    const date=t=>t==null?'Not recorded':window.meshcorestationFormatDate(t);
    const visible=()=>$('repeater-performance-disclosure')?.open&&$('repeater-optimizer-disclosure')?.open;
    const drafts=new Map();let attached=false,controller=null,writer=null,generation=0,key='',selectedMarker=null,comparisonDays=7,lastData=null,lastWidth=0;
    const labels={companion_packets:'Companion path packets',distinct_packets:'Distinct observed packet IDs',observed_routes:'Observed route patterns',companion_network_packets:'All Companion network packets',analyzer_hourly_relays_mean:'Mean Analyzer hourly relays',analyzer_neighbors_mean:'Mean observed neighboring repeaters',analyzer_bidirectional_mean:'Mean confirmed bidirectional relationships',optimizer_neighbors_mean:'Mean optimizer neighbor records',analyzer_pairs_mean:'Mean Analyzer communication pairs served (rolling window)',analyzer_routes_mean:'Mean returned Analyzer route patterns'};
    function stop(){++generation;controller?.abort();controller=null;writer?.abort();writer=null;}
    function table(headers,rows){const wrap=node('div',null,'stats-table-scroll'),table=node('table'),head=node('tr');headers.forEach(h=>head.append(node('th',h)));const thead=node('thead');thead.append(head);table.append(thead);const body=node('tbody');for(const cells of rows){const tr=node('tr');for(const v of cells){const td=node('td');td.append(v instanceof Node?v:document.createTextNode(String(v)));tr.append(td);}body.append(tr);}table.append(body);wrap.append(table);return wrap;}
    function compare(id){selectedMarker=id;load(true);}
    const disclosures=new Map();
    function disclosure(title,id){const section=node('details',null,'stats-section performance-disclosure');section.id=id;section.open=disclosures.get(id)||false;section.append(node('summary',title));section.addEventListener('toggle',()=>disclosures.set(id,section.open));return section;}
    function chart(title,data,series){
        const box=node('section',null,'stats-section');box.append(node('h3',title));
        const legend=node('div',null,'stats-controls muted');for(const [,label,color] of series){const item=node('span',null,'performance-series'),line=node('span',null,'performance-swatch');line.style.borderTopColor=color;line.setAttribute('aria-hidden','true');item.append(line,document.createTextNode(label));legend.append(item);}box.append(legend,node('p','Blank intervals mean no saved observations. Vertical lines mark logged changes.','muted'));
        const width=Math.max(320,Math.min(900,$('performance-content').clientWidth||900)),plot=width-70;
        box.classList.add('performance-chart-section');
        if(!data.timeline.some(p=>series.some(s=>p[s[0]]!=null)))box.append(node('p','No saved observations for this chart in the selected window. This does not mean zero activity.','stats-message'));
        const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('class','stats-chart performance-chart');svg.setAttribute('viewBox',`0 0 ${width} 240`);svg.setAttribute('role','group');svg.setAttribute('aria-label',title);
        const add=(tag,attrs,text)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!=null)e.textContent=text;svg.append(e);return e;};
        const integerAxis=series.every(s=>['neighbors','two_way','optimizer_neighbors','hourly_relays'].includes(s[0]));const begin=data.start,end=data.now,rawScale=Math.max(1,...data.timeline.flatMap(p=>series.map(s=>p[s[0]]??0))),scale=integerAxis?Math.ceil(rawScale):rawScale,x=t=>50+plot*(t-begin)/(end-begin),y=v=>185-155*v/scale;
        add('path',{d:`M50 25V185H${width-20}`,fill:'none',stroke:'var(--border)'});
        const ticks=integerAxis?Math.min(scale,width<600?2:3):(width<600?2:3);for(let i=0;i<=ticks;i++){const value=integerAxis?Math.round(scale*i/ticks):scale*i/ticks;add('text',{x:44,y:y(value)+4,'text-anchor':'end'},Number(value).toLocaleString('en-US',{notation:'compact',maximumFractionDigits:1}));const at=begin+(end-begin)*i/ticks;const label=new Intl.DateTimeFormat('en-GB',{timeZone:window.meshcorestationDisplaySettings?.timezone||'Europe/Berlin',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(at*1000));add('text',{x:x(at),y:215,'text-anchor':i===0?'start':i===ticks?'end':'middle'},label);}
        for(const [field,label,color] of series){let path='',active=false;
            for(const p of data.timeline){const v=p[field];if(v==null){active=false;continue;}const bucketed=field==='copies'||field==='network',stamp=bucketed?p.at:field==='hourly_relays'?(p.hourly_at??p.at):field==='optimizer_neighbors'?(p.optimizer_at??p.at):(p.analyzer_at??p.at);const at=Math.max(begin,Math.min(end,bucketed?p.at+data.step/2:stamp));path+=(active?'L':'M')+x(at)+' '+y(v);active=true;const dot=add('circle',{cx:x(at),cy:y(v),r:2,fill:color});const tip=document.createElementNS(ns,'title');tip.textContent=`${date(stamp)} · ${label}: ${fmt(v)}`;dot.append(tip);}
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
        try{const response=await fetch('/api/repeater-performance',{method:'POST',headers:{'Content-Type':'application/json','X-Meshcore-Control':'1'},body:JSON.stringify({...body,public_key:target,revision:lastData?.revision||0}),signal:write.signal});const r=await response.json();if(!response.ok||!r.ok)throw Error(r.error||'Could not save the change marker.');if(version!==generation||target!==key||!visible())return;success?.();if(body.action==='delete'&&selectedMarker===body.id)selectedMarker=null;await load();}
        catch(e){if(version===generation&&(e.name!=='AbortError'||timedOut))$('performance-status').textContent='Change marker request failed: '+(timedOut?'request timed out; refresh saved data before retrying.':e.message);}
        finally{clearTimeout(timeout);if(writer===write)writer=null;if(version===generation)button.disabled=false;}
    }
    function journal(host,data){
        const section=node('section',null,'stats-section performance-journal');section.append(node('h3','Recorded changes'),node('p','Swipe or scroll the table horizontally to reach all columns.','muted performance-scroll-hint'));
        if(!data.markers.length)section.append(node('p','No changes logged for this repeater.'));
        else section.append(table(['When','Change','Source','Actions'],data.markers.map(m=>{
            const buttons=node('div',null,'stats-controls');const open=node('button','Compare'),edit=node('button','Edit'),remove=node('button','Delete');open.onclick=()=>compare(m.id);edit.onclick=()=>{const input=localInput(m.at);drafts.set(key,{id:m.id,description:m.description,time:input,originalInput:input,originalAt:m.at});render(data);$('performance-description').focus();};remove.onclick=()=>{if(window.confirm('Delete this local marker? This does not change the repeater or its configuration audit.'))mutate({action:'delete',id:m.id},remove);};buttons.append(open,edit,remove);
            const source=node('span',m.source_id?'Verified configuration record':'Manual journal entry');if(m.source_id){const details=node('details');details.append(node('summary','Original audit details'),node('p','Recorded at '+date(m.source_at)),node('p',m.provenance));source.append(details);}return [date(m.at),m.description,source,buttons];
        })));host.append(section);
    }
    function comparison(host,data){
        if(!data.comparison)return;const c=data.comparison,section=node('section',null,'stats-section');section.id='performance-comparison';const marker=data.markers.find(m=>m.id===selectedMarker);section.append(node('h3','Before/after: '+(marker?.description||'Recorded change')));
        const label=node('label','Equal observation windows'),select=node('select');for(const [value,text] of [[1,'24 hours before/after'],[3,'3 days before/after'],[7,'7 days before/after']]){const option=node('option',text);option.value=value;select.append(option);}select.value=comparisonDays;select.onchange=()=>{comparisonDays=Number(select.value);load(true);};label.append(select);section.append(label);
        for(const name of ['before','after']){const w=c.windows[name];section.append(node('p',`${name==='before'?'Before':'After'}: ${date(w.start)} → ${date(w.end)}. Analyzer samples: ${w.analyzer_samples}/${w.expected_hourly_samples} (${w.analyzer_source||'Saved hourly samples'}); reach snapshots: ${w.analyzer_snapshot_samples??0}. Companion buckets with received packets: ${w.companion_buckets_with_packets}. Optimizer samples: ${w.optimizer_samples}. Elapsed through ${date(w.observed_until)}; Companion first/last: ${date(w.first_companion)} / ${date(w.last_companion)}.`,'muted'));}
        section.append(node('p','Swipe or scroll the table horizontally to see all comparison values.','muted performance-scroll-hint'));
        section.append(table(['Measurement','Before','After','Difference','Percent change (observed only)'],Object.keys(labels).filter(field=>c.differences[field]).map(field=>{const v=c.differences[field];return [labels[field],fmt(v.before),fmt(v.after),fmt(v.absolute),v.percent==null?(v.reason||'Not available (missing/zero baseline)'):fmt(v.percent)+'%'];})));
        section.append(node('p',c.interpretation));for(const warning of c.warnings)section.append(node('p',warning,'stats-message'));host.append(section);
    }
    function charts(data){const hourly=data.hourly_timeline?{...data,timeline:data.hourly_timeline,step:3600}:data;return [chart('Companion observations',data,[['copies','Packets involving this repeater','var(--accent)'],['network','All received network packets','var(--muted)']]),chart('Analyzer hourly forwarding',hourly,[[data.hourly_timeline?'hourly_relays':'relay_1h',data.hourly_timeline?'Packets in each recorded hour':'Legacy rolling 1h relay count','var(--accent)']]),chart('Analyzer Network Reach',data,[['neighbors','Neighboring repeaters','var(--accent)'],['two_way','Confirmed bidirectional observations','var(--green)'],['optimizer_neighbors','Optimizer neighbor records (reception only)','var(--muted)']])];}
    function render(data){
        lastData=data;names().ingest(data.repeaters||[]);const host=$('performance-content');host.replaceChildren();$('performance-selected').replaceChildren(names().element(key));
        const l=data.local,a=data.analyzer,s=data.summary||{},details=s.details||{};
        const overview=node('section',null,'performance-overview');overview.append(node('h3','Performance Overview'),node('p','Is it active? How does it help? Is observed activity changing?','muted'));
        const cards=node('div',null,'stats-metrics');
        const age=a?`Snapshot retrieved ${date(a.at)}.`:'No Analyzer snapshot is available.';
        for(const [title,value,explanation] of [
            ['Mesh Activity',s.activity||(l.copies>0?'Activity observed':'No recent evidence'),`${fmt(l.copies)} Companion path packets in the selected period. ${fmt(s.hourly_total)} Analyzer relays across recorded hours. These are separate observations, not delivery counts.`],
            ['Network Reach',a?fmt(a.neighbors)+' neighboring repeaters':'No recent connectivity evidence',`${fmt(a?.two_way)} bidirectional relationships inferred from observations. ${age} ${s.snapshot_recent?'':'This snapshot may be old.'}`],
            ['Mesh Contribution',details.pairs!=null?fmt(details.pairs)+' communication pairs served':fmt(l.routes)+' observed route patterns',`Analyzer rolling-window pairs and Companion route patterns describe involvement, not verified delivery. ${fmt(l.unique)} distinct Companion packet IDs involved this repeater.`],
            ['Performance Trend',s.trend||'Not enough complete history to assess a trend.',`${s.hourly_observed??0}/${s.hourly_expected??0} complete hourly observations available. ${s.trend_complete?'Equal periods have hourly evidence; this is an activity trend, not a quality score.':'Missing hours prevent a reliable improvement or decline assessment.'}`]
        ]){const card=node('div',null,'stats-metric');card.append(node('p',title,'muted'),node('strong',value),node('p',explanation,'muted'));cards.append(card);}overview.append(cards);
        const quality=node('div',null,'performance-quality');quality.append(node('h4','Data completeness'),node('p',`Analyzer hourly history: ${fmt(s.hourly_observed)} / ${fmt(s.hourly_expected)} hours in the selected period. First / latest recorded hour: ${date(s.first_hour)} / ${date(s.last_hour)}.`));
        const schedule=s.collection;
        quality.append(node('p',schedule?`Automatic collection: ${schedule.error||schedule.state||'Scheduled'}. Last success: ${date(schedule.success_at)}. Next attempt: ${date(schedule.next_at)}.`:'The server schedules Analyzer collection every 12 hours for managed repeaters. Collection status will appear after its first scheduling pass.'));
        quality.append(node('p',s.network_context||`${fmt(l.network)} separately received Companion network packets provide traffic context. Continuous reception coverage is unknown.`,'muted'),node('p',s.explanation||'Activity is observed involvement, not proof of packet delivery.','muted'));overview.append(quality);host.append(overview);
        if(l.error)host.append(node('p',l.error,'stats-message'));
        const technical=disclosure('Detailed Statistics','performance-details');
        technical.append(table(['Source','Measurement','Observed value'],[
            ['Companion','Path packet copies',fmt(l.copies)],['Companion','Distinct packet IDs',fmt(l.unique)],['Companion','Route patterns',fmt(l.routes)],['Companion','All received network packets (separate context)',fmt(l.network)],['Companion','Ambiguous paths excluded',fmt(l.ambiguous)],
            ['Analyzer','Rolling 1h / 24h relay counts',fmt(a?.relay_1h)+' / '+fmt(a?.relay_24h)],['Analyzer','Neighboring repeaters / bidirectional observations',fmt(a?.neighbors)+' / '+fmt(a?.two_way)],['Analyzer','Communication pairs (reported rolling window)',fmt(details.pairs)],['Analyzer','Returned route patterns (may be truncated)',fmt(details.routes)],['Analyzer graph','Degree / betweenness / rank',fmt(a?.degree)+' / '+(details.betweenness==null?'Not available':Number(details.betweenness).toLocaleString('en-US',{maximumSignificantDigits:6}))+' / '+fmt(details.graph_rank)],['Optimization Analysis','Neighbor reception records',fmt(data.optimizer_neighbors?.observed)]
        ]));technical.append(node('p','Companion source: '+l.source+'. Sources are never added together.','muted'));data.notes.forEach(note=>technical.append(node('p',note,'muted')));host.append(technical);
        const history=disclosure('Performance History','performance-history');history.append(node('p','Companion charts show local received path copies. Analyzer charts show provider observations. Blank intervals are unknown, not zero. Neighbor relationships are inferred.','muted'),...charts(data));host.append(history);
        const changes=disclosure('Performance Changes','performance-changes');
        if(selectedMarker||drafts.get(key)?.id)changes.open=true;
        editor(changes,data);journal(changes,data);comparison(changes,data);host.append(changes);
    }

    async function load(scroll=false){
        if(!visible())return;await window.meshcorestationEnsureRepeaterSelection?.();if(!visible())return;
        const next=window.meshcorestationSelectedRepeater||'';if(next!==key){key=next;selectedMarker=null;lastData=null;$('performance-content').replaceChildren();}stop();const version=generation;
        if(!key){$('performance-status').textContent='Select a managed repeater in Repeater Management.';$('performance-selected').textContent='No repeater selected';return;}
        $('performance-selected').replaceChildren(names().element(key));controller=new AbortController();const active=controller;let timedOut=false;const timeout=setTimeout(()=>{timedOut=true;active.abort();},15000);$('performance-content').setAttribute('aria-busy','true');$('performance-status').textContent='Loading saved performance observations…';
        try{const response=await fetch(`/api/repeater-performance?public_key=${encodeURIComponent(key)}&days=${$('performance-days').value}${selectedMarker?'&marker_id='+selectedMarker+'&compare_days='+comparisonDays:''}`,{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal:active.signal});const data=await response.json();if(version!==generation||!visible())return;if(!response.ok||!data.ok)throw Error(data.error||'Performance data unavailable.');if(data.public_key!==key||!data.local||!Array.isArray(data.notes)||!Array.isArray(data.timeline)||!Array.isArray(data.markers))throw Error('Invalid performance response.');render(data);$('performance-status').textContent='Saved observations loaded. Gaps are not zero activity. Refresh saved data does not contact the radio or analyzer.';if(scroll){$('performance-history').open=true;$('performance-changes').open=true;$('performance-comparison')?.scrollIntoView?.({block:'start'});}}
        catch(e){if(version===generation&&(e.name!=='AbortError'||timedOut))$('performance-status').textContent='Performance unavailable: '+(timedOut?'request timed out.':e.message)+' Existing displayed observations may be outdated.';}
        finally{clearTimeout(timeout);if(version===generation)$('performance-content')?.setAttribute('aria-busy','false');}
    }
    function attach(){if(attached||!$('performance-content'))return;attached=true;const toggle=()=>{if(visible())load();else{stop();$('performance-content').setAttribute('aria-busy','false');}};$('repeater-performance-disclosure').addEventListener('toggle',toggle);$('repeater-optimizer-disclosure').addEventListener('toggle',toggle);$('performance-days').onchange=()=>load();$('performance-refresh').onclick=()=>load();document.addEventListener('managed-repeater-selected',()=>{stop();key='';selectedMarker=null;lastData=null;$('performance-content').replaceChildren();if(visible())load();});document.addEventListener('repeater-network-updated',e=>{if(visible()&&e.detail===key&&!writer)load();});if(window.ResizeObserver)new ResizeObserver(()=>{const width=$('performance-content').clientWidth;if(visible()&&lastData?.public_key===key&&width!==lastWidth){lastWidth=width;const old=[...$('performance-content').querySelectorAll('.performance-chart-section')],fresh=charts(lastData);old.forEach((n,i)=>n.replaceWith(fresh[i]));}}).observe($('performance-content'));if(visible())load();}
    new MutationObserver(attach).observe(document.documentElement,{subtree:true,childList:true});attach();
})();
