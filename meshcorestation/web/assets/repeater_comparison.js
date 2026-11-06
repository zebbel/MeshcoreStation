/* Local journal and saved-only comparisons; no polling or radio commands. */
(() => {
    const $=id=>document.getElementById(id),text=(tag,value,cls)=>{const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;};
    const stamp=value=>window.meshcorestationFormatDate?.(value)||new Date(value*1000).toLocaleString();
    let attached=false,key='',rows=[],offset=0,epoch=0,requestNumber=0,pending=null;
    const headers={'X-Meshcore-Control':'1'};
    function cancel(){epoch++;requestNumber++;pending?.abort();pending=null;}
    async function request(url,body,signal){
        const response=await fetch(url,{method:body?'POST':'GET',headers:body?{...headers,'Content-Type':'application/json'}:headers,cache:'no-store',body:body?JSON.stringify(body):undefined,signal});
        const value=await response.json();if(!response.ok||!value.ok)throw Error(value.error||'Saved data unavailable.');return value;
    }
    function identity(r){return window.MeshcoreStationRepeaterNames?.element(r.public_key)||text('span',r.name||r.public_key);}
    function percentageChange(before,after){
        if(!Number.isFinite(before)||!Number.isFinite(after))return 'Unavailable';
        if(before===0)return 'N/A';
        const rounded=Number(((after-before)/before*100).toFixed(1));
        return (rounded>0?'+':rounded<0?'−':'')+Math.abs(rounded).toFixed(1)+'%';
    }
    function table(host,head,data){const table=document.createElement('table'),tr=document.createElement('tr');for(const label of head)tr.append(text('th',label));table.append(tr);for(const cells of data){const row=document.createElement('tr');for(const value of cells){const cell=document.createElement('td');cell.append(value instanceof Node?value:text('span',value));row.append(cell);}table.append(row);}const scroll=text('div','','statistics-table-scroll');scroll.append(table);host.append(scroll);}
    function button(label,action){const n=text('button',label,'secondary');n.type='button';n.addEventListener('click',action);return n;}
    function journal(selected=$('comparison-change').value){
        rows.sort((a,b)=>a.recorded_at-b.recorded_at||a.id-b.id);
        const host=$('comparison-journal');host.replaceChildren();
        if(!rows.length)host.append(text('p','No changes recorded for this repeater.','muted'));
        else table(host,['Recorded time','Change Description','Actions'],rows.map(row=>{
            const controls=document.createElement('div');controls.className='comparison-actions';
            controls.append(button('Edit',()=>edit(row)),button('Delete',()=>remove(row)));
            return [stamp(row.recorded_at),row.description,controls];
        }));
        const select=$('comparison-change');select.replaceChildren(new Option('Select a saved change',''));
        for(const row of rows)select.add(new Option(stamp(row.recorded_at)+' · '+row.description,String(row.id)));
        select.value=rows.some(r=>String(r.id)===String(selected))?String(selected):'';
        $('comparison-run').disabled=!select.value;
    }
    async function load(more=false,extra=null){
        if(!$('repeater-comparison-disclosure')?.open)return;
        cancel();const ticket=epoch;const chosen=$('comparison-change').value;
        $('comparison-status').textContent='Loading change history…';$('comparison-error').textContent='';
        const controller=new AbortController();pending=controller;const timer=setTimeout(()=>controller.abort(),5000);
        try{
            const params=new URLSearchParams({offset:String(more?offset:0)});if(key)params.set('public_key',key);
            const data=await request('/api/repeater-comparison/changes?'+params,null,controller.signal);
            if(ticket!==epoch)return;
            if(key!==data.selected)$('comparison-results').replaceChildren();
            key=data.selected;window.MeshcoreStationRepeaterNames?.ingest(data.repeaters);
            const picker=$('comparison-repeater');picker.replaceChildren();for(const r of data.repeaters)picker.add(new Option(window.MeshcoreStationRepeaterNames?.label(r.public_key)||r.name||r.public_key,r.public_key));picker.value=key;picker.disabled=!key;
            $('comparison-save').disabled=!key;
            const all=[...(more?rows:[]),...data.changes,...(extra?[extra]:[])];rows=[...new Map(all.map(r=>[r.id,r])).values()];offset=(more?offset:0)+data.changes.length;
            $('comparison-more').hidden=!data.has_more;journal(extra?.id||chosen);
            $('comparison-status').textContent=key?'Changes loaded. Select a change to compare saved observations.':'Add a managed repeater to record changes.';
        }catch(error){if(ticket===epoch)$('comparison-error').textContent=error.name==='AbortError'?'Change history request timed out. Saved changes are preserved.':error.message;}
        finally{clearTimeout(timer);if(pending===controller)pending=null;}
    }
    async function mutate(action,row,description){
        const target=key,ticket=epoch;const body={action,public_key:target};if(row)body.id=row.id;if(description!==undefined)body.description=description;if(action==='delete')body.confirm=true;
        $('comparison-save').disabled=true;
        try{
            const data=await request('/api/repeater-comparison/changes',body,AbortSignal.timeout(5000));
            if(target!==key||ticket!==epoch)return;
            $('comparison-results').replaceChildren();$('comparison-results').classList.remove('statistics-stale');
            if(action==='create')$('comparison-description').value='';
            if(action==='delete'&&$('comparison-change').value===String(row.id)){$('comparison-results').replaceChildren();$('comparison-change').value='';}
            await load(false,data.change);$('comparison-status').textContent=action==='delete'?'Change deleted; statistics are preserved.':'Change saved; the original recorded time is retained when editing.';
        }catch(error){if(target===key)$('comparison-error').textContent=error.name==='TimeoutError'?'Save response timed out. Refresh changes before saving again; the request may have completed.':error.message;}
        finally{$('comparison-save').disabled=!key;}
    }
    function edit(row){const value=window.prompt('Edit change description (recorded time stays unchanged)',row.description);if(value!==null)mutate('edit',row,value);}
    function remove(row){if(window.confirm('Delete this change record? Historical statistics will remain.\n'+row.description))mutate('delete',row);}
    function metric(v,suffix=''){return v==null?'Unavailable':Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:2})+suffix:String(v);}
    function delta(v,suffix=''){return v==null?'Insufficient Data':(v>0?'+':'')+v.toFixed(2)+suffix;}
    function render(data){
        const host=$('comparison-results');host.replaceChildren();window.MeshcoreStationRepeaterNames?.ingest([...data.matched,...(data.source_changes||[]),...data.newly_heard,...data.not_heard_after,...data.new_observed_neighbors,...data.not_observed_after]);
        host.append(text('h3',data.change.description),text('p','Recorded: '+stamp(data.change.recorded_at)),text('p','Saved comparison snapshot: '+stamp(data.generated_at),'muted'));
        const warnings=document.createElement('ul');warnings.className='comparison-warnings';for(const w of data.warnings)warnings.append(text('li',w));host.append(warnings);
        table(host,['','Before','After'],[['Window',stamp(data.before.start)+' — '+stamp(data.before.end),stamp(data.after.start)+' — '+stamp(data.after.end)],['Recording coverage',...['before','after'].map(k=>{const p=data[k];return metric(p.recorded_seconds/3600,' h')+' / '+metric(p.expected_seconds/3600,' h')+' · '+(p.future?'Incomplete (future)':p.complete?'Complete':'Incomplete / unknown');})],['Distinct valid SNR samples',data.before.snr_samples,data.after.snr_samples]]);
        host.append(text('h3','Neighbor SNR Comparison'),text('p','Matched-neighbor median observed SNR change: '+delta(data.median_snr_change,' dB'),'comparison-median'),text('p',data.interpretation,'muted'));
        if(!data.matched.length)host.append(text('p','Insufficient Data — no unambiguously identified neighbors with valid samples in both periods.'));
        else table(host,['Neighbor','Before','After','Change'],data.matched.map(r=>[identity(r),text('span',metric(r.before,' dB')+' · '+r.before_samples+' samples','comparison-before'),text('span',metric(r.after,' dB')+' · '+r.after_samples+' samples','comparison-after'),text('strong',delta(r.difference_db,' dB'),r.difference_db>0?'comparison-positive':r.difference_db<0?'comparison-negative':'muted')]));
        if(data.source_changes?.length){host.append(text('p','SNR source changed — these values are not directly compared or included in the median.'));table(host,['Neighbor','Before','After'],data.source_changes.map(r=>[identity(r),metric(r.before,' dB')+' · '+r.before_samples+' samples · '+(r.before_source==='firmware_aggregates'?'Firmware aggregates':'Legacy last-heard estimates'),metric(r.after,' dB')+' · '+r.after_samples+' samples · '+(r.after_source==='firmware_aggregates'?'Firmware aggregates':'Legacy last-heard estimates')]));}
        for(const [label,list]of [['Newly heard — SNR observed after only',data.newly_heard],['Not heard after — SNR observed before only',data.not_heard_after]]){
            host.append(text('h4',label));if(!list.length)host.append(text('p','None in the saved observations.','muted'));
            else table(host,['Neighbor','Observed mean','Samples','Last Heard'],list.map(r=>[identity(r),metric(r.average_snr,' dB'),r.samples,stamp(r.last_heard)]));
        }
        host.append(text('h3','Supporting Observations'));
        const metrics=[['Observed neighbors','neighbors',''],['Confirmed observed receptions','receptions',''],['Unique packets','unique_packets',''],['Repeated receptions','repeated',''],['Unidentified receptions','unidentified',''],['Covered receptions / recorded hour','traffic_per_recorded_hour',' / h'],['One-way observed relationships','one_way',''],['Two-way observed relationships','two_way','']];
        table(host,['Measurement','Before','After','Difference','Change (%)'],metrics.map(([label,k,suffix])=>[label,metric(data.before[k],suffix),metric(data.after[k],suffix),data.before[k]==null||data.after[k]==null?'Unavailable':metric(data.after[k]-data.before[k],suffix),percentageChange(data.before[k],data.after[k])]));
        for(const [label,list]of [['Newly observed route neighbors',data.new_observed_neighbors],['Route neighbors not observed after',data.not_observed_after]]){host.append(text('h4',label+' · '+list.length));const names=document.createElement('ul');for(const r of list){const li=document.createElement('li');li.append(identity(r));names.append(li);}host.append(names);}
        host.append(text('p','Covered traffic rates use receptions inside recorded healthy collection intervals only. Missing coverage is not zero traffic. Relationships come from observed flood routes, not verified direct RF links. SNR Last Heard times are estimates.','muted'));
        for(const period of ['before','after']){const notes=document.createElement('details');notes.append(text('summary',period==='before'?'Before — data limitations':'After — data limitations'));for(const n of data[period].notes)notes.append(text('p',n,'muted'));notes.append(text('p',data[period].uncertain_snr_groups+' unknown/ambiguous SNR groups excluded from identity matching.'));host.append(notes);}
        if(data.overlapping_changes.length){host.append(text('h4','Other changes in these windows'));const list=document.createElement('ul');for(const r of data.overlapping_changes)list.append(text('li',stamp(r.recorded_at)+' · '+r.description));host.append(list);if(data.overlap_limit)host.append(text('p','Showing the first 200 overlapping changes.'));}
    }
    async function compare(){
        if(!$('repeater-comparison-disclosure').open||!key||!$('comparison-change').value)return;
        pending?.abort();const controller=new AbortController();pending=controller;const ticket=++requestNumber,target=key;
        const timer=setTimeout(()=>controller.abort(),10000);$('comparison-status').textContent='Calculating saved before/after observations…';$('comparison-error').textContent='';
        $('comparison-results').classList.add('statistics-stale');
        try{
            const params=new URLSearchParams({public_key:key,change_id:$('comparison-change').value,days:$('comparison-period').value});
            const data=await request('/api/repeater-comparison/view?'+params,null,controller.signal);
            if(ticket!==requestNumber||target!==key||!$('repeater-comparison-disclosure').open)return;
            render(data);$('comparison-results').classList.remove('statistics-stale');$('comparison-status').textContent='Saved comparison loaded. Partial periods are preliminary; no radio requests were made.';
        }catch(error){if(ticket===requestNumber)$('comparison-error').textContent=error.name==='AbortError'?'Comparison request timed out. Any faded results are a previous snapshot.':error.message;}
        finally{clearTimeout(timer);if(pending===controller)pending=null;}
    }
    function attach(){if(attached||!$('repeater-comparison-disclosure'))return;attached=true;
        $('repeater-comparison-disclosure').addEventListener('toggle',()=>{$('repeater-comparison-disclosure').open?load():cancel();});
        $('comparison-repeater').addEventListener('change',()=>{key=$('comparison-repeater').value;rows=[];offset=0;$('comparison-change').replaceChildren();$('comparison-results').replaceChildren();load();});
        $('comparison-save').addEventListener('click',()=>mutate('create',null,$('comparison-description').value));
        $('comparison-more').addEventListener('click',()=>load(true));$('comparison-refresh').addEventListener('click',()=>load());
        $('comparison-change').addEventListener('change',()=>{cancel();$('comparison-run').disabled=!$('comparison-change').value;$('comparison-results').replaceChildren();compare();});
        $('comparison-period').addEventListener('change',compare);$('comparison-run').addEventListener('click',compare);
        document.addEventListener('managed-repeater-removed',()=>{if($('repeater-comparison-disclosure').open){key='';$('comparison-results').replaceChildren();load();}});
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
