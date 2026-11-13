/* Local journal and saved-only comparisons; no polling or radio commands. */
(() => {
    const {t: ui, translatedError: uiError = value => value} = window.MeshcoreStationI18n || {
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`))
    };
    const $=id=>document.getElementById(id),text=(tag,value,cls)=>{const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;};
    const stamp=value=>window.meshcorestationFormatDate?.(value)||new Date(value*1000).toLocaleString();
    let attached=false,key='',rows=[],offset=0,epoch=0,pending=null,comparison=null;
    const headers={'X-Meshcore-Control':'1'};
    function controls() {
        $('comparison-run').disabled = !!pending || !!comparison || !key || !$('comparison-change').value;
    }
    function cancelComparison() {
        if (!comparison) return;
        comparison.abort();
        comparison = null;
        $('comparison-status').textContent = ui('Comparison cancelled.');
        controls();
    }
    function cancel() {
        epoch++;
        pending?.abort();
        pending = null;
        cancelComparison();
        controls();
    }
    function fail(message) {
        $('comparison-status').textContent = '';
        $('comparison-error').textContent = message;
    }
    async function request(url,body,signal){
        const response=await fetch(url,{method:body?'POST':'GET',headers:body?{...headers,'Content-Type':'application/json'}:headers,cache:'no-store',body:body?JSON.stringify(body):undefined,signal});
        const value=await response.json();if(!response.ok||!value.ok)throw Error(value.error_code==='QUERY_TIMEOUT'
            ? ui(value.resume ? 'Comparison reached its time limit during {0}. Run it again to resume from saved progress.' : 'Comparison reached its time limit during {0}. Try again or select a shorter period.', ui(value.stage))
            : value.error||ui("Saved data unavailable."));return value;
    }
    function identity(r){return window.MeshcoreStationRepeaterNames?.element(r.public_key)||text('span',r.name||r.public_key);}
    function percentageChange(before,after){
        if(!Number.isFinite(before)||!Number.isFinite(after))return ui("Unavailable");
        if(before===0)return 'N/A';
        const rounded=Number(((after-before)/before*100).toFixed(1));
        return (rounded>0?'+':rounded<0?'−':'')+Math.abs(rounded).toFixed(1)+'%';
    }
    function table(host,head,data){const table=document.createElement('table'),tr=document.createElement('tr');for(const label of head)tr.append(text('th',label));table.append(tr);for(const cells of data){const row=document.createElement('tr');for(const value of cells){const cell=document.createElement('td');cell.append(value instanceof Node?value:text('span',value));row.append(cell);}table.append(row);}const scroll=text('div','','statistics-table-scroll');scroll.append(table);host.append(scroll);}
    function button(label,action){const n=text('button',label,'secondary');n.type='button';n.addEventListener('click',action);return n;}
    function journal(selected=$('comparison-change').value){
        rows.sort((a,b)=>a.recorded_at-b.recorded_at||a.id-b.id);
        const host=$('comparison-journal');host.replaceChildren();
        if(!rows.length)host.append(text('p',ui("No changes recorded for this repeater."),'muted'));
        else table(host,[ui("Recorded time"),ui("Change Description"),ui("Actions")],rows.map(row=>{
            const controls=document.createElement('div');controls.className='comparison-actions';
            controls.append(button(ui("Edit"),()=>edit(row)),button(ui("Delete"),()=>remove(row)));
            return [stamp(row.recorded_at),row.description,controls];
        }));
        const select=$('comparison-change');select.replaceChildren(new Option(ui("Select a saved change"),''));
        for(const row of rows)select.add(new Option(stamp(row.recorded_at)+' · '+row.description,String(row.id)));
        select.value=rows.some(r=>String(r.id)===String(selected))?String(selected):'';
        controls();
    }
    async function load(more=false,extra=null){
        if(!$('repeater-comparison-disclosure')?.open)return;
        cancel();const ticket=epoch;const chosen=$('comparison-change').value;
        $('comparison-status').textContent=ui("Loading change history…");$('comparison-error').textContent='';
        const controller=new AbortController();
        pending=controller;
        controls();
        const timer=setTimeout(()=>{
            if(pending!==controller)return;
            controller.abort();
            pending=null;
            epoch++;
            fail(ui('Change history request timed out. Saved changes are preserved.'));
            controls();
        },5000);
        controller.signal.addEventListener('abort',()=>clearTimeout(timer),{once:true});
        try{
            const params=new URLSearchParams({offset:String(more?offset:0)});if(key)params.set('public_key',key);
            const data=await request('/api/repeater-comparison/changes?'+params,null,controller.signal);
            if(ticket!==epoch)return;
            if(key!==data.selected)$('comparison-results').classList.add('statistics-stale');
            key=data.selected;window.MeshcoreStationRepeaterNames?.ingest(data.repeaters);
            const picker=$('comparison-repeater');picker.replaceChildren();for(const r of data.repeaters)picker.add(new Option(window.MeshcoreStationRepeaterNames?.label(r.public_key)||r.name||r.public_key,r.public_key));picker.value=key;picker.disabled=!key;
            $('comparison-save').disabled=!key;
            const all=[...(more?rows:[]),...data.changes,...(extra?[extra]:[])];rows=[...new Map(all.map(r=>[r.id,r])).values()];offset=(more?offset:0)+data.changes.length;
            $('comparison-more').hidden=!data.has_more;journal(extra?.id||chosen);
            $('comparison-status').textContent=key?ui("Changes loaded. Select a change to compare saved observations."):ui("Add a managed repeater to record changes.");
            return true;
        }catch(error){if(ticket===epoch)fail(uiError(error.message));}
        finally{clearTimeout(timer);if(pending===controller){pending=null;controls();}}
    }
    async function mutate(action,row,description){
        const target=key,ticket=epoch;const body={action,public_key:target};if(row)body.id=row.id;if(description!==undefined)body.description=description;if(action==='delete')body.confirm=true;
        $('comparison-save').disabled=true;
        try{
            const data=await request('/api/repeater-comparison/changes',body,AbortSignal.timeout(5000));
            if(target!==key||ticket!==epoch)return;
            $('comparison-results').classList.add('statistics-stale');
            if(action==='create')$('comparison-description').value='';
            if(action==='delete'&&$('comparison-change').value===String(row.id)){$('comparison-change').value='';}
            if(await load(false,data.change))$('comparison-status').textContent=action==='delete'?ui("Change deleted; statistics are preserved."):ui("Change saved; the original recorded time is retained when editing.");
        }catch(error){if(target===key&&ticket===epoch)$('comparison-error').textContent=error.name==='TimeoutError'?ui("Save response timed out. Refresh changes before saving again; the request may have completed."):uiError(error.message);}
        finally{$('comparison-save').disabled=!key;}
    }
    function edit(row){const value=window.prompt(ui("Edit change description (recorded time stays unchanged)"),row.description);if(value!==null)mutate('edit',row,value);}
    function remove(row){if(window.confirm(ui("Delete this change record? Historical statistics will remain.\n")+row.description))mutate('delete',row);}
    function metric(v,suffix=''){return v==null?ui("Unavailable"):Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:2})+suffix:String(v);}
    function delta(v,suffix=''){return v==null?ui("Insufficient Data"):(v>0?'+':'')+v.toFixed(2)+suffix;}
    function render(data){
        const host=document.createDocumentFragment();window.MeshcoreStationRepeaterNames?.ingest([...data.matched,...(data.source_changes||[]),...data.newly_heard,...data.not_heard_after,...data.new_observed_neighbors,...data.not_observed_after]);
        host.append(text('h3',data.change.description),text('p',ui("Recorded: ")+stamp(data.change.recorded_at)),text('p',ui("Saved comparison snapshot: ")+stamp(data.generated_at),'muted'));
        const warnings=document.createElement('ul');warnings.className='comparison-warnings';for(const w of data.warnings)warnings.append(text('li',ui(w)));host.append(warnings);
        table(host,['',ui("Before"),ui("After")],[[ui("Window"),stamp(data.before.start)+' — '+stamp(data.before.end),stamp(data.after.start)+' — '+stamp(data.after.end)],[ui("Recording coverage"),...['before','after'].map(k=>{const p=data[k];return metric(p.recorded_seconds/3600,' h')+' / '+metric(p.expected_seconds/3600,' h')+' · '+(p.future?ui("Incomplete (future)"):p.complete?ui("Complete"):ui("Incomplete / unknown"));})],[ui("Distinct valid SNR samples"),data.before.snr_samples,data.after.snr_samples]]);
        host.append(text('h3',ui("Neighbor SNR Comparison")),text('p',ui("Matched-neighbor median observed SNR change: ")+delta(data.median_snr_change,' dB'),'comparison-median'),text('p',ui(data.interpretation),'muted'));
        if(!data.matched.length)host.append(text('p',ui("Insufficient Data — no unambiguously identified neighbors with valid samples in both periods.")));
        else table(host,[ui("Neighbor"),ui("Before"),ui("After"),ui("Change")],data.matched.map(r=>[identity(r),text('span',metric(r.before,' dB')+' · '+r.before_samples+ui(' samples'),'comparison-before'),text('span',metric(r.after,' dB')+' · '+r.after_samples+ui(' samples'),'comparison-after'),text('strong',delta(r.difference_db,' dB'),r.difference_db>0?'comparison-positive':r.difference_db<0?'comparison-negative':'muted')]));
        if(data.source_changes?.length){host.append(text('p',ui("SNR source changed — these values are not directly compared or included in the median.")));table(host,[ui("Neighbor"),ui("Before"),ui("After")],data.source_changes.map(r=>[identity(r),metric(r.before,' dB')+' · '+r.before_samples+ui(" samples · ")+(r.before_source==='firmware_aggregates'?ui("Firmware aggregates"):ui("Legacy last-heard estimates")),metric(r.after,' dB')+' · '+r.after_samples+ui(" samples · ")+(r.after_source==='firmware_aggregates'?ui("Firmware aggregates"):ui("Legacy last-heard estimates"))]));}
        for(const [label,list]of [[ui("Newly heard — SNR observed after only"),data.newly_heard],[ui("Not heard after — SNR observed before only"),data.not_heard_after]]){
            host.append(text('h4',label));if(!list.length)host.append(text('p',ui("None in the saved observations."),'muted'));
            else table(host,[ui("Neighbor"),ui("Observed mean"),ui("Samples"),ui("Last Heard")],list.map(r=>[identity(r),metric(r.average_snr,' dB'),r.samples,stamp(r.last_heard)]));
        }
        host.append(text('h3',ui("Supporting Observations")));
        const metrics=[[ui("Observed neighbors"),'neighbors',''],[ui("Confirmed observed receptions"),'receptions',''],[ui("Unique packets"),'unique_packets',''],[ui("Repeated receptions"),'repeated',''],[ui("Unidentified receptions"),'unidentified',''],[ui("Covered receptions / recorded hour"),'traffic_per_recorded_hour',' / h'],[ui("One-way observed relationships"),'one_way',''],[ui("Two-way observed relationships"),'two_way','']];
        table(host,[ui("Measurement"),ui("Before"),ui("After"),ui("Difference"),ui("Change (%)")],metrics.map(([label,k,suffix])=>[label,metric(data.before[k],suffix),metric(data.after[k],suffix),data.before[k]==null||data.after[k]==null?ui("Unavailable"):metric(data.after[k]-data.before[k],suffix),percentageChange(data.before[k],data.after[k])]));
        for(const [label,list]of [[ui("Newly observed route neighbors"),data.new_observed_neighbors],[ui("Route neighbors not observed after"),data.not_observed_after]]){host.append(text('h4',label+' · '+list.length));const names=document.createElement('ul');for(const r of list){const li=document.createElement('li');li.append(identity(r));names.append(li);}host.append(names);}
        host.append(text('p',ui("Covered traffic rates use receptions inside recorded healthy collection intervals only. Missing coverage is not zero traffic. Relationships come from observed flood routes, not verified direct RF links. SNR Last Heard times are estimates."),'muted'));
        for(const period of ['before','after']){const notes=document.createElement('details');notes.append(text('summary',period==='before'?ui("Before — data limitations"):ui("After — data limitations")));for(const n of data[period].notes)notes.append(text('p',ui(n),'muted'));notes.append(text('p',data[period].uncertain_snr_groups+ui(" unknown/ambiguous SNR groups excluded from identity matching.")));host.append(notes);}
        if(data.overlapping_changes.length){host.append(text('h4',ui("Other changes in these windows")));const list=document.createElement('ul');for(const r of data.overlapping_changes)list.append(text('li',stamp(r.recorded_at)+' · '+r.description));host.append(list);if(data.overlap_limit)host.append(text('p',ui("Showing the first 200 overlapping changes.")));}
        $('comparison-results').replaceChildren(host);
    }
    async function compare(){
        if (!$('repeater-comparison-disclosure').open || pending || comparison || !key || !$('comparison-change').value) return;
        const controller = new AbortController();
        comparison = controller;
        controls();
        const params = new URLSearchParams({
            public_key: key, change_id: $('comparison-change').value, days: $('comparison-period').value
        });
        $('comparison-status').textContent = ui('Calculating saved before/after observations…');
        $('comparison-error').textContent = '';
        $('comparison-results').classList.add('statistics-stale');
        const timer = setTimeout(() => {
            if (comparison !== controller) return;
            controller.abort();
            comparison = null;
            fail(ui('Comparison request timed out. Any faded results are a previous snapshot.'));
            controls();
        }, 10000);
        controller.signal.addEventListener('abort', () => clearTimeout(timer), {once:true});
        try {
            const data = await request('/api/repeater-comparison/view?' + params, null, controller.signal);
            if (comparison !== controller) return;
            if (!$('repeater-comparison-disclosure').open) {
                cancelComparison();
                return;
            }
            render(data);
            $('comparison-results').classList.remove('statistics-stale');
            $('comparison-status').textContent = ui('Saved comparison loaded. Partial periods are preliminary; no radio requests were made.');
        } catch (error) {
            if (comparison === controller) {
                fail(uiError(error.message));
            }
        } finally {
            clearTimeout(timer);
            if (comparison === controller) {
                comparison = null;
                controls();
            }
        }
    }
    function selectionChanged() {
        cancelComparison();
        $('comparison-results').classList.add('statistics-stale');
        controls();
        compare();
    }
    function attach(){if(attached||!$('repeater-comparison-disclosure'))return;attached=true;
        $('repeater-comparison-disclosure').addEventListener('toggle',()=>{$('repeater-comparison-disclosure').open?load():(cancel(), $('comparison-status').textContent='');});
        $('comparison-repeater').addEventListener('change',()=>{key=$('comparison-repeater').value;rows=[];offset=0;$('comparison-change').replaceChildren();$('comparison-results').classList.add('statistics-stale');load();});
        $('comparison-save').addEventListener('click',()=>mutate('create',null,$('comparison-description').value));
        $('comparison-more').addEventListener('click',()=>load(true));$('comparison-refresh').addEventListener('click',()=>load());
        $('comparison-change').addEventListener('change',selectionChanged);
        $('comparison-period').addEventListener('change',selectionChanged);$('comparison-run').addEventListener('click',compare);
        document.addEventListener('managed-repeater-removed',()=>{if($('repeater-comparison-disclosure').open){key='';$('comparison-results').classList.add('statistics-stale');load();}});
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
