/* Saved observations and explicit manual Analyzer refresh. No polling or radio commands. */
(() => {
    const $=id=>document.getElementById(id), names=()=>window.MeshcoreStationRepeaterNames;
    const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=String(text);if(cls)e.className=cls;return e;};
    const fmt=n=>n==null?'Not available':Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
    const date=t=>t==null?'Not recorded':window.meshcorestationFormatDate(t);
    const visible=()=>$('repeater-performance-disclosure')?.open&&$('repeater-optimizer-disclosure')?.open;
    const drafts=new Map();let attached=false,controller=null,writer=null,generation=0,loadIntent=0,key='',selectedMarker=null,comparisonDays=7,lastData=null,lastWidth=0,neighborMap=null;
    const labels={companion_packets:'Companion path packets',distinct_packets:'Distinct observed packet IDs',observed_routes:'Observed route patterns',companion_network_packets:'All Companion network packets',analyzer_hourly_relays_mean:'Mean Analyzer hourly relays',analyzer_neighbors_mean:'Mean observed neighboring repeaters',analyzer_bidirectional_mean:'Mean confirmed bidirectional relationships',optimizer_neighbors_mean:'Mean optimizer neighbor records',analyzer_pairs_mean:'Mean Analyzer communication pairs served (rolling window)',analyzer_sole_pairs_mean:'Mean Analyzer sole-observed route pairs',analyzer_routes_mean:'Mean returned Analyzer route patterns'};
    function stop(){++generation;controller?.abort();controller=null;writer?.abort();writer=null;if($('performance-refresh'))$('performance-refresh').disabled=false;}
    function table(headers,rows){const wrap=node('div',null,'stats-table-scroll'),table=node('table'),head=node('tr');headers.forEach(h=>head.append(node('th',h)));const thead=node('thead');thead.append(head);table.append(thead);const body=node('tbody');for(const cells of rows){const tr=node('tr');for(const v of cells){const td=node('td');td.append(v instanceof Node?v:document.createTextNode(String(v)));tr.append(td);}body.append(tr);}table.append(body);wrap.append(table);return wrap;}
    function compare(id){selectedMarker=id;load(true);}
    const disclosures=new Map();
    function disclosure(title,id){const section=node('details',null,'stats-section performance-disclosure');section.id=id;section.open=disclosures.get(id)||false;section.append(node('summary',title));section.addEventListener('toggle',()=>disclosures.set(id,section.open));return section;}
    function chart(title,view,series,id,explanation){
        const box=node('section',null,'stats-section performance-chart-section');box.id=id;box.dataset.chart=title;box.append(node('h3',title));
        const legend=node('div',null,'stats-controls muted');for(const [,label,color] of series){const item=node('span',null,'performance-series'),line=node('span',null,'performance-swatch');line.style.borderTopColor=color;line.setAttribute('aria-hidden','true');item.append(line,document.createTextNode(label));legend.append(item);}box.append(legend);
        const rows=view.timeline,width=Math.max(320,Math.min(1100,$('performance-content').clientWidth||900)),plot=width-76;
        if(!rows.some(p=>series.some(s=>p[s[0]]!=null)))box.append(node('p','Insufficient Data — no comparable saved observations in this window.','stats-message'));
        const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('class','stats-chart performance-chart');svg.setAttribute('viewBox',`0 0 ${width} 250`);svg.setAttribute('role','group');svg.setAttribute('aria-label',title);
        const add=(tag,attrs,text)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!=null)e.textContent=text;svg.append(e);return e;};
        const integerAxis=series.every(s=>['neighbors','two_way','pairs','sole_pairs','hourly_relays'].includes(s[0]));
        const begin=view.start,end=view.end,maximum=Math.max(1,...rows.flatMap(p=>series.map(s=>p[s[0]]??0))),ticks=integerAxis?Math.min(Math.ceil(maximum),width<600?2:4):(width<600?2:4),scale=integerAxis?Math.ceil(maximum/ticks)*ticks:maximum,x=t=>56+plot*(t-begin)/(end-begin),y=v=>190-160*v/scale;
        add('path',{d:`M56 25V190H${width-20}`,fill:'none',stroke:'var(--border)'});
        for(let i=0;i<=ticks;i++){
            const value=integerAxis?Math.round(scale*i/ticks):scale*i/ticks;
            add('path',{d:`M56 ${y(value)}H${width-20}`,stroke:'var(--border)','stroke-dasharray':'2 5',fill:'none',opacity:.45});
            add('text',{x:49,y:y(value)+4,'text-anchor':'end',class:'performance-y-label'},Number(value).toLocaleString('en-US',{notation:integerAxis?'standard':'compact',maximumFractionDigits:integerAxis?0:1}));
        }
        const dates=width<600?2:4;for(let i=0;i<=dates;i++){const at=begin+(end-begin)*i/dates;const label=new Intl.DateTimeFormat('en-GB',{timeZone:window.meshcorestationDisplaySettings?.timezone||'Europe/Berlin',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(at*1000));add('text',{x:x(at),y:222,'text-anchor':i===0?'start':i===dates?'end':'middle'},label);}
        for(const [field,label,color] of series){let path='',active=false;
            for(const p of rows){const v=p[field];if(v==null){active=false;continue;}const stamp=p.stamp??p.at,at=Math.max(begin,Math.min(end,stamp));path+=(active?'L':'M')+x(at)+' '+y(v);active=true;
                const dot=add('circle',{cx:x(at),cy:y(v),r:rows.length>48?2:3,fill:color,'data-series':field,'data-value':v,'data-at':stamp});const tip=document.createElementNS(ns,'title');tip.textContent=`${date(stamp)} · ${label}: ${fmt(v)}`;
                if(field.endsWith('_index'))tip.textContent+=` · Companion raw copies: repeater ${fmt(p.copies)}, mesh ${fmt(p.network)}`;dot.append(tip);
            }
            add('path',{d:path,fill:'none',stroke:color,'stroke-width':2.5,class:'performance-data-line','data-series':field});
        }
        for(const marker of view.markers.filter(m=>m.at>=begin&&m.at<=end)){
            const line=add('rect',{x:x(marker.at)-8,y:18,width:16,height:177,fill:'transparent',class:'performance-change-line',tabindex:0,role:'button','aria-label':marker.description});
            add('path',{d:`M${x(marker.at)} 18V195`,stroke:'var(--accent)','stroke-width':marker.id===selectedMarker?4:2,'stroke-dasharray':'5 4',class:'performance-marker-line','pointer-events':'none','aria-hidden':'true'});
            const tip=document.createElementNS(ns,'title');tip.textContent=marker.description+' · '+date(marker.at);line.append(tip);line.addEventListener('click',()=>compare(marker.id));line.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();compare(marker.id);}});
        }
        box.append(svg,node('h4','What does this mean?'),node('p',explanation,'muted'));
        const detail=node('details');detail.append(node('summary','Show measured values'));
        detail.append(table(['Observation time',...series.map(s=>s[1]),...(series[0][0].endsWith('_index')?['Repeater copies','Mesh copies']:[])],rows.map(p=>[date(p.stamp??p.at),...series.map(s=>fmt(p[s[0]])),...(series[0][0].endsWith('_index')?[fmt(p.copies),fmt(p.network)]:[])])));box.append(detail);return box;
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
        catch(e){if(version===generation&&(e.name!=='AbortError'||timedOut))$('performance-status').textContent='Change marker request failed: '+(timedOut?'request timed out; reopen Performance to check saved markers before retrying.':e.message);}
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
    const series={
        forwarding:[['hourly_relays','Analyzer relay events per complete hour','var(--accent)']],
        relative:[['repeater_index','Repeater involvement (index)','var(--accent)'],['mesh_index','Companion-observed mesh traffic (index)','var(--green)']],
        connectivity:[['neighbors','Observed repeater neighbors','var(--accent)'],['two_way','Bidirectional observations','var(--green)']],
        routing:[['pairs','Communication pairs served','var(--accent)'],['sole_pairs','Sole-observed route pairs','var(--green)']]
    };
    const domainTitles={forwarding:'Forwarding Activity',relative:'Repeater vs. Mesh Activity',connectivity:'Network Connectivity',routing:'Routing Contribution'};
    function charts(data,comparison=false){
        const v=comparison?data.comparison.dashboard:data.dashboard,prefix=comparison?'comparison':'performance';
        const baseline=v.companion.baseline;
        const explanations={
            forwarding:'Peaks mean more observed forwarding; quiet recorded hours mean fewer events. Blank hours have no measurements. Changes may reflect traffic or observer coverage, not delivery quality.',
            relative:baseline?`Both Companion lines start at 100 in the same complete bucket (${date(baseline.at)}). A faster-rising repeater line means greater involvement relative to observed mesh traffic. Sources share the same reception stream; coverage and routing can still change.`:'Insufficient Data for an index: a complete Companion bucket with positive repeater and mesh counts is required. Analyzer counts are never divided by Companion traffic.',
            connectivity:'These are sampled Analyzer observations of neighbors and bidirectional relationships. A relationship is inferred, not a verified direct radio link. Blank collection intervals remain gaps.',
            routing:'Analyzer rolling 24-hour pair counts describe observed path involvement. Sole-observed pairs had no alternative in the Analyzer observations; this does not prove an exclusive route or successful delivery.'
        };
        return Object.keys(series).map(domain=>chart((comparison?'Before/after — ':'')+domainTitles[domain],{start:v.start,end:v.end,markers:data.markers,timeline:domain==='forwarding'?v.forwarding:domain==='relative'?v.companion.timeline:v.snapshots},series[domain],`${prefix}-${domain}`,explanations[domain]));
    }
    const fieldLabels={hourly_relays:'Mean hourly relay events',copies:'Mean repeater path copies per bucket',network:'Mean observed mesh copies per bucket',neighbors:'Mean observed neighbors',two_way:'Mean bidirectional relationships',pairs:'Mean communication pairs',sole_pairs:'Mean sole-observed pairs'};
    function assessment(view,id,title){
        const section=node('section',null,'stats-section performance-assessment');section.id=id;section.append(node('h3',title),node('p',view.overall,'performance-assessment-summary'),node('p',view.interpretation,'muted'));
        for(const [domain,a] of Object.keys(series).map(k=>[k,view.assessment[k]])){
            const item=node('article',null,'performance-assessment-item');item.append(node('h4',domainTitles[domain]),node('strong',a.status));
            for(const [field,change] of Object.entries(a.changes)){item.append(node('p',`${fieldLabels[field]}: ${fmt(change.before)} → ${fmt(change.after)} (${change.percent==null?'percentage unavailable':(change.percent>0?'+':'')+fmt(change.percent)+'%'}).`));}
            item.append(node('p',a.explanation,'muted'),node('p',`Historical coverage, earlier / later: ${a.coverage.available.map((n,i)=>fmt(n)+'/'+fmt(a.coverage.expected[i])).join(' / ')} observed intervals.`,'muted'));section.append(item);
        }
        section.append(node('p',view.caution,'muted'));return section;
    }
    function comparison(host,data){
        if(!data.comparison)return;const c=data.comparison,section=node('section',null,'stats-section');section.id='performance-comparison';const marker=data.markers.find(m=>m.id===selectedMarker);section.append(node('h3','Before/after: '+(marker?.description||'Recorded change')));
        const label=node('label','Equal observation windows'),select=node('select');for(const [value,text] of [[1,'24 hours before/after'],[3,'3 days before/after'],[7,'7 days before/after']]){const option=node('option',text);option.value=value;select.append(option);}select.value=comparisonDays;select.onchange=()=>{comparisonDays=Number(select.value);load(true);};label.append(select);section.append(label);
        for(const name of ['before','after']){const w=c.windows[name];section.append(node('p',`${name==='before'?'Before':'After'}: ${date(w.start)} → ${date(w.end)}. Hourly Analyzer coverage: ${w.analyzer_samples}/${w.expected_hourly_samples}.`,'muted'));}
        if(c.dashboard){section.append(...charts(data,true),assessment(c.dashboard,'comparison-assessment','Before/after assessment'));}
        for(const warning of c.warnings)section.append(node('p',warning,'stats-message'));
        const values=node('details',null,'comparison-values');values.append(node('summary','Detailed before/after values'),node('p','Swipe or scroll horizontally to see all values.','muted performance-scroll-hint'));
        values.append(node('p',c.interpretation),node('p','Detailed values retain exact Companion windows and hourly sampled Analyzer means. Dashboard connectivity and routing trends use one snapshot per 12-hour interval; these are sampled observations, not time-weighted guarantees.','muted'),table(['Measurement','Before','After','Difference','Percent change (observed only)'],Object.keys(labels).filter(field=>c.differences[field]).map(field=>{const v=c.differences[field];return [labels[field],fmt(v.before),fmt(v.after),fmt(v.absolute),v.percent==null?(v.reason||'Not available (missing/zero baseline)'):fmt(v.percent)+'%'];})));section.append(values);host.append(section);
    }
    function technical(data){
        const l=data.local,a=data.analyzer,s=data.summary||{},d=s.details||{},v=data.dashboard,technical=disclosure('Detailed Statistics','performance-details');
        technical.append(node('p','Swipe or scroll horizontally to see all technical values.','muted performance-scroll-hint'),table(['Source','Measurement','Observed value'],[
            ['Companion','Path packet copies',fmt(l.copies)],['Companion','Distinct packet IDs',fmt(l.unique)],['Companion','Route patterns',fmt(l.routes)],['Companion','All received network packets (separate context)',fmt(l.network)],['Companion','Ambiguous paths excluded',fmt(l.ambiguous)],['Companion','First / latest observations in selected history',date(l.first)+' / '+date(l.last)],['Analyzer history','Available / expected complete hourly buckets',fmt(s.hourly_observed)+' / '+fmt(s.hourly_expected)],['Analyzer history','First / latest saved complete hour',date(s.first_hour)+' / '+date(s.last_hour)],
            ['Analyzer','Rolling 1h / 24h relay counts',fmt(a?.relay_1h)+' / '+fmt(a?.relay_24h)],['Analyzer','Neighboring repeaters / bidirectional observations',fmt(a?.neighbors)+' / '+fmt(a?.two_way)],['Analyzer','Communication pairs (rolling 24h)',fmt(d.pairs)],['Analyzer','Sole-observed pairs (rolling 24h)',fmt(v.cards.sole_pairs)],['Analyzer','Returned route patterns (may be truncated)',fmt(d.routes)],['Analyzer graph','Degree / betweenness / rank',fmt(a?.degree)+' / '+(d.betweenness==null?'Not available':Number(d.betweenness).toLocaleString('en-US',{maximumSignificantDigits:6}))+' / '+fmt(d.graph_rank)],['Optimization Analysis','Neighbor reception records',fmt(data.optimizer_neighbors?.observed)],['Optimization Analysis','Neighbor records timestamp',date(data.optimizer_neighbors?.at)]
        ]));
        technical.append(node('p','Statistics source: '+l.source+'. The indexed chart independently uses only comparable Companion network observations.','muted'));
        const schedule=s.collection;technical.append(node('p',schedule?`Automatic collection: ${schedule.error||schedule.state||'Scheduled'}. Last success: ${date(schedule.success_at)}. Next attempt: ${date(schedule.next_at)}.`:'Analyzer collection runs every 12 hours while the station service runs.','muted'));
        if(v.companion.error)technical.append(node('p',v.companion.error,'stats-message'));data.notes.forEach(note=>technical.append(node('p',note,'muted')));return technical;
    }
    function render(data){
        neighborMap?.dispose();neighborMap=null;lastData=data;names().ingest(data.repeaters||[]);const host=$('performance-content');host.replaceChildren();$('performance-selected').replaceChildren(names().element(key));
        const v=data.dashboard,c=v.cards,overview=node('section',null,'performance-overview');overview.id='performance-contribution';overview.append(node('h3','Mesh Contribution'));
        overview.append(node('p',c.at?`Latest Analyzer rolling 24h: ${date(c.at-86400)} → ${date(c.at)}. Retrieved ${date(c.at)}. Cards keep this period when the history selector changes.`:'No saved Analyzer snapshot. Measurements are unavailable, not zero.','muted'));
        if(c.at&&data.now-c.at>13*3600)overview.append(node('p','Older Analyzer snapshot — collection or external access may be unavailable.','stats-message'));
        const cards=node('div',null,'stats-metrics');
        for(const [title,value,extra,explanation] of [
            ['Relay Activity',fmt(c.relay_24h),'Observed events / rolling 24h','Observed relay events, not confirmed message deliveries.'],
            ['Two-Way Reach',c.two_way==null||c.neighbors==null?'Not available':fmt(c.two_way)+' / '+fmt(c.neighbors),c.two_way_percent==null?'Percentage unavailable':fmt(c.two_way_percent)+'% of observed neighbors','Bidirectional / total observed repeater neighbors. Inferred relationships, not verified direct links.'],
            ['Communication Pairs Served',fmt(c.pairs),'Observed pairs / rolling 24h','Pairs whose observed paths involve this repeater. Not a delivery-success count.'],
            ['Sole-Observed Route Pairs',fmt(c.sole_pairs),'Observed pairs / rolling 24h','No alternative route was observed by the Analyzer. Other routes may exist.']
        ]){const card=node('div',null,'stats-metric');card.dataset.metric=title;card.append(node('p',title,'muted'),node('strong',value),node('p',extra,'performance-unit'),node('p',explanation,'muted'));cards.append(card);}overview.append(cards);host.append(overview);
        const mainCharts=charts(data);neighborMap=window.MeshcoreStationNeighborMap.create(data.neighbor_map,key,visible);host.append(...mainCharts.slice(0,3),neighborMap.element,mainCharts[3],assessment(v,'performance-assessment','Performance Assessment'));
        const changes=disclosure('Performance Changes','performance-changes');if(selectedMarker||drafts.get(key)?.id)changes.open=true;
        editor(changes,data);journal(changes,data);comparison(changes,data);host.append(changes,technical(data));
        if(data.local.error)host.append(node('p',data.local.error,'stats-message'));
    }

    function validView(v){return v&&Number.isFinite(v.start)&&Number.isFinite(v.end)&&v.end>v.start&&v.cards&&Array.isArray(v.forwarding)&&Array.isArray(v.snapshots)&&Array.isArray(v.companion?.timeline)&&Object.keys(series).every(k=>v.assessment?.[k]?.coverage&&v.assessment[k].changes);}
    async function load(scroll=false,refresh=false,auto=false){
        if(!visible())return;const intent=++loadIntent;await window.meshcorestationEnsureRepeaterSelection?.();if(!visible()||intent!==loadIntent)return;
        const next=window.meshcorestationSelectedRepeater||'';if(next!==key){key=next;selectedMarker=null;lastData=null;$('performance-content').replaceChildren();}stop();const version=generation;
        if(!key){$('performance-status').textContent='Select a managed repeater in Repeater Management.';$('performance-selected').textContent='No repeater selected';return;}
        $('performance-selected').replaceChildren(names().element(key));controller=new AbortController();const active=controller;let timedOut=false;const timeout=setTimeout(()=>{timedOut=true;active.abort();},refresh?35000:15000);$('performance-refresh').disabled=true;$('performance-content').setAttribute('aria-busy','true');$('performance-status').textContent=refresh?'Refreshing Analyzer measurements… Saved observations remain visible.':'Loading saved performance observations…';
        try{const response=await fetch(`/api/repeater-performance?public_key=${encodeURIComponent(key)}&days=${$('performance-days').value}${refresh?'&refresh='+(refresh===true?'1':refresh):''}${selectedMarker?'&marker_id='+selectedMarker+'&compare_days='+comparisonDays:''}`,{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal:active.signal});const data=await response.json();if(version!==generation||!visible())return;if(!response.ok||!data.ok)throw Error(data.error||'Performance data unavailable.');if(data.public_key!==key||!data.local||!Array.isArray(data.notes)||!Array.isArray(data.timeline)||!Array.isArray(data.markers)||!validView(data.dashboard)||(data.comparison&&!validView(data.comparison.dashboard)))throw Error('Invalid performance response.');if(refresh&&!data.analyzer_refresh)throw Error('Analyzer refresh result missing; saved observations retained.');const attempt=data.analyzer_refresh;if(refresh!=='auto'||attempt?.state!=='cached'||data.neighbor_map?.fetched_at!==lastData?.neighbor_map?.fetched_at)render(data);$('performance-status').textContent=refresh?(attempt?.error?'Analyzer refresh failed: '+attempt.error+' Previously saved observations were retained.':attempt?.history_error?'Analyzer snapshot refreshed. '+attempt.history_error:attempt?.state==='cached'?'Recent shared Analyzer cache reused. Saved observations loaded.':'Analyzer refreshed. Cards, history charts and neighbor map updated from the saved response.'):'Saved observations loaded. Gaps are not zero activity. Refresh saved data requests fresh Analyzer measurements; it sends no radio commands.';if(scroll){$('performance-changes').open=true;$('performance-comparison')?.scrollIntoView?.({block:'start'});}}
        catch(e){if(version===generation&&(e.name!=='AbortError'||timedOut))$('performance-status').textContent='Performance unavailable: '+(timedOut?'request timed out.':e.message)+' Existing displayed observations may be outdated.';}
        finally{clearTimeout(timeout);if(version===generation){controller=null;$('performance-content')?.setAttribute('aria-busy','false');$('performance-refresh').disabled=false;}}
        if(auto&&version===generation&&visible()&&lastData?.public_key===key)await load(false,'auto');
    }
    function attach(){if(attached||!$('performance-content'))return;attached=true;const toggle=()=>{if(visible()){if(!controller){neighborMap?.resize();load(false,false,true);}}else{stop();$('performance-content').setAttribute('aria-busy','false');}};$('repeater-performance-disclosure').addEventListener('toggle',toggle);$('repeater-optimizer-disclosure').addEventListener('toggle',toggle);$('performance-days').onchange=()=>load();$('performance-refresh').onclick=()=>load(false,true);document.addEventListener('managed-repeater-selected',()=>{stop();neighborMap?.dispose();neighborMap=null;key='';selectedMarker=null;lastData=null;$('performance-content').replaceChildren();if(visible())load(false,false,true);});document.addEventListener('repeater-network-updated',e=>{if(visible()&&e.detail===key&&!writer)load();});if(window.ResizeObserver)new ResizeObserver(()=>{const width=$('performance-content').clientWidth;if(visible()&&lastData?.public_key===key&&width!==lastWidth){lastWidth=width;const old=[...$('performance-content').querySelectorAll('.performance-chart-section')],fresh=[...charts(lastData),...(lastData.comparison?.dashboard?charts(lastData,true):[])];old.forEach((n,i)=>{if(fresh[i]){fresh[i].querySelector('details').open=n.querySelector('details').open;n.replaceWith(fresh[i]);}});}}).observe($('performance-content'));if(visible())load(false,false,true);}
    new MutationObserver(attach).observe(document.documentElement,{subtree:true,childList:true});attach();
})();
