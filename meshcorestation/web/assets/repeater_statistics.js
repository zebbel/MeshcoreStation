/* Independent view only: membership and continuous collection belong to the server. */
(() => {
    const {translatedError: uiError, t: ui} = window.MeshcoreStationI18n || {
        translatedError: value => value,
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`))
    };
    const $ = id => document.getElementById(id);
    let attached=false, selected='', sequence=0, monitorKey='';
    const requests=new Set();
    function stop(){window.MeshcoreStationNeighborReadNow?.stop();sequence++;for(const request of requests)request.abort();requests.clear();}
    async function requestJSON(url,timeout,kind){
        const controller=new AbortController();requests.add(controller);let timedOut=false;
        const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeout);
        try{
            const response=await fetch(url,{cache:'no-store',signal:controller.signal,...(url.includes('/neighbor-monitor')?{headers:{'X-Meshcore-Control':'1'}}:{})});
            let value;try{value=await response.json();}catch{throw Error(ui("The {0} response was unreadable. Existing history is preserved.", ui(kind)));}
            if(!response.ok||!value.ok){
                const error=Error(value.error||ui("The {0} request failed.", ui(kind)));error.code=value.error_code;error.status=response.status;throw error;
            }
            return value;
        }catch(error){
            if(timedOut){const timeoutError=Error(kind==='recording status'?ui("Recording-status request timed out in the browser (5 seconds)."):ui("Saved-statistics request timed out in the browser (10 seconds); recording status remains available."));timeoutError.code='BROWSER_TIMEOUT';throw timeoutError;}
            throw error;
        }finally{clearTimeout(timer);requests.delete(controller);}
    }
    async function loadMonitoring(key,ticket,preserveControls=false){
        const form=$('neighbor-monitor-settings');if(!form)return;if(!preserveControls){form.disabled=true;monitorKey='';}if(!preserveControls&&$('neighbor-monitor-summary'))$('neighbor-monitor-summary').textContent=ui("Loading settings…");
        if(!key){$('neighbor-monitor-status').textContent=ui("Select a managed repeater to configure neighbor monitoring.");return;}
        try{
            const data=await requestJSON('/api/repeater-statistics/neighbor-monitor?public_key='+encodeURIComponent(key),5000,"neighbor monitoring settings");
            if(ticket!==sequence||selected!==key)return;
            if(!preserveControls){$('neighbor-monitor-enabled').checked=!!data.config.enabled;$('neighbor-monitor-interval').value=data.config.interval_minutes;form.disabled=false;}
            monitorKey=key;window.MeshcoreStationNeighborReadNow?.load(key);
            const cfg=data.config;
            $('neighbor-monitor-status').textContent=(cfg.enabled?ui("Enabled · ")+cfg.interval_minutes+ui(" minutes · ")+(data.running?ui(cfg.state):ui("worker unavailable / Companion disconnected")):ui("Disabled"))+
                (cfg.last_success?ui(" · Last complete poll: ")+(window.meshcorestationFormatDate?.(cfg.last_success)||new Date(cfg.last_success*1000).toLocaleString()):'')+
                (cfg.error?' · '+cfg.error:'');
            const protocol=data.protocol||{},names={averaged:ui("Averaged"),legacy:ui("Legacy"),unknown:ui("Unknown")};
            const format=v=>v==null?ui("Not recorded"):window.meshcorestationFormatDate?.(v)||new Date(v*1000).toLocaleString();
            const diagnostic=protocol.diagnostics||{},details=$('neighbor-monitor-protocol-details');
            if(details){details.replaceChildren();for(const [label,value]of [
                [ui("Detected SNR protocol"),names[protocol.capability]||ui("Unknown")],[ui("Detection status"),protocol.detection ? ui(protocol.detection.replace(/_/g,' ')) : ui('Unprobed')],
                [ui("Last successful collection"),format(protocol.last_collection||cfg.last_success)],
                [ui("Last completed aggregation window"),diagnostic.retained?ui("Boot {0} · window {1}", String(protocol.session||'').slice(0,8), diagnostic.newest_window):ui("Not recorded")],
                [ui("Latest saved UTC window end"),format(protocol.last_window)],[ui("Next scheduled collection"),cfg.enabled?format(cfg.next_due):ui("Not scheduled")],
                [ui("Records retrieved"),protocol.records_retrieved??0],[ui("Collection duration"),protocol.duration_seconds==null?ui("Not recorded"):Number(protocol.duration_seconds).toFixed(1)+' seconds'],
                [ui("Collection completeness"),protocol.completeness ? ui(protocol.completeness.replace(/_/g,' ')) : ui('Not collected')],
                [ui("Firmware boot counters (cumulative)"),ui("Expired: {0} · Evicted: {1} · Dropped: {2}", diagnostic.expired??0, diagnostic.evicted??0, diagnostic.dropped??0)],
                [ui("Retained sequence range"),`${diagnostic.oldest??0}–${diagnostic.newest??0}`],[ui("Warnings"),protocol.warning||ui("None")],[ui("Last protocol error"),protocol.error||ui("None")]]){
                    const row=document.createElement('p');row.textContent=label+': '+value;details.append(row);
                }}
            if($('neighbor-monitor-summary'))$('neighbor-monitor-summary').textContent=$('neighbor-monitor-status').textContent+ui(" · Interval: ")+cfg.interval_minutes+ui(" min · Last success: ")+(cfg.last_success?(window.meshcorestationFormatDate?.(cfg.last_success)||cfg.last_success):ui("None"));
        }catch(error){if(ticket===sequence){$('neighbor-monitor-status').textContent=ui("Monitoring settings unavailable: ")+uiError(error.message);if($('neighbor-monitor-summary'))$('neighbor-monitor-summary').textContent=ui("Settings unavailable · ")+uiError(error.message);}}
    }
    async function load(preserveMonitoring=false){
        const section=$('repeater-statistics-disclosure');if(!section?.open||document.hidden)return;
        stop();const ticket=sequence;
        window.MeshcoreStationStatisticsVisuals?.stale?.();
        const progress=$('statistics-view-status');if(progress){progress.textContent=ui("Loading saved observations… Recording continues independently.");progress.setAttribute('aria-busy','true');}
        if($('statistics-view-error'))$('statistics-view-error').textContent='';
        let data;
        try{
            data=await requestJSON('/api/repeater-statistics/status'+(selected?'?public_key='+encodeURIComponent(selected):''),5000,"recording status");
            if(ticket!==sequence||!section.open)return;
            window.MeshcoreStationRepeaterNames?.ingest(data.repeaters);
            const picker=$('statistics-repeater');picker.replaceChildren();
            for(const repeater of data.repeaters){
                const option=new Option(window.MeshcoreStationRepeaterNames?.label(repeater.public_key)||repeater.name||ui("Unknown Repeater ({0}…)", repeater.public_key.slice(0,8)),repeater.public_key);
                option.title=repeater.public_key;option.dataset.repeaterKey=repeater.public_key;picker.add(option);
            }
            selected=data.selected;picker.value=selected;picker.disabled=!data.repeaters.length;
            if(!selected){picker.add(new Option(ui("No managed repeaters"),''));$('statistics-status').textContent=ui("Add a repeater in Repeater Management to begin passive recording.");}
            else{
                const health=data.health,state=!health.running?ui("Collector stopped"):!health.connected?ui("Companion disconnected; saved history remains available"):ui("Recording");
                const count=data.observation_count===null?ui("Saved count unavailable"):ui("{0} saved observations (all time)", data.observation_count);
                const last=data.last_recorded_at?(window.meshcorestationFormatDate?.(data.last_recorded_at)||new Date(data.last_recorded_at*1000).toLocaleString('en-GB')):ui("No observations recorded yet");
                $('statistics-status').textContent=ui("{0}. {1}. Last recorded: {2}.", state, count, last);
            }
            loadMonitoring(selected,ticket,preserveMonitoring===true);
            const health=data.health;
            $('statistics-error').textContent=[uiError(data.error),uiError(health.error),uiError(health.repeater_error),health.dropped?ui("{0} observations or repeater writes dropped this session; recording is incomplete.", health.dropped):'',health.invalid?ui("{0} malformed/unsupported packet events skipped this session.", health.invalid):''].filter(Boolean).join(' ');
        }catch(error){
            if(ticket!==sequence||!section.open)return;
            if(error.status===400)selected='';
            $('statistics-error').textContent=uiError(error.message);
            if($('statistics-status').textContent&&!$('statistics-status').textContent.startsWith(ui('Last available status')))$('statistics-status').textContent=ui("Last available status — ")+$('statistics-status').textContent;
            if(progress){progress.textContent=ui("Recording status unavailable. Refresh to try again.");progress.setAttribute('aria-busy','false');}
            return;
        }
        try{
            if($('statistics-hourly')){
                const params=new URLSearchParams({days:$('statistics-period').value||'1'});if(selected)params.set('public_key',selected);
                // A fresh independent budget starts after status has been rendered.
                const view=await requestJSON('/api/repeater-statistics/view?'+params,10000,"saved statistics");
                if(ticket!==sequence||!section.open)return;
                if(view.selected!==selected)throw Error(ui("Managed repeater selection changed. Refresh the saved view."));
                window.MeshcoreStationStatisticsVisuals?.render(view);
                if(progress)progress.textContent=ui("Saved observations loaded.");
            }
        }catch(error){
            if(ticket!==sequence||!section.open)return;
            const category=error.code==='QUERY_TIMEOUT'?ui("Server query timeout: "):error.code==='DATABASE_BUSY'?ui("Database busy: "):error.code==='DATABASE_ERROR'?ui("Database error: "):error.code==='STATISTICS_BUSY'?ui("Statistics calculation busy: "):'';
            ($('statistics-view-error')||$('statistics-error')).textContent=category+uiError(error.message);
            if(progress)progress.textContent=ui("Statistics could not be refreshed. Recording status above remains available; faded charts are an older snapshot.");
        }finally{if(ticket===sequence&&progress)progress.setAttribute('aria-busy','false');}
    }
    window.MeshcoreStationRefreshSavedSnr=()=>load(true);
    function attach(){
        const section=$('repeater-statistics-disclosure');if(attached||!section)return;attached=true;
        section.addEventListener('toggle',()=>{if(section.open)load();else{stop();}});
        function clearView(){window.MeshcoreStationStatisticsVisuals?.dispose();for(const id of ['statistics-neighbor-snr','statistics-active-neighbors','statistics-heatmap','statistics-packet-types','statistics-hourly','statistics-hops','statistics-regions','statistics-coverage','statistics-map-notes','statistics-missing-coordinates','statistics-ambiguous'])$(id)?.replaceChildren();}
        if($('statistics-one-way-host')){const input=document.createElement('input');input.type='checkbox';input.id='statistics-show-one-way';input.checked=true;$('statistics-one-way-host').append(input);}
        if($('neighbor-monitor-checkbox-host')){
            const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.id='neighbor-monitor-enabled';$('neighbor-monitor-checkbox-host').append(checkbox);
        }
        $('neighbor-monitor-save')?.addEventListener('click',async()=>{
            if(!monitorKey||monitorKey!==selected)return;
            const key=monitorKey,form=$('neighbor-monitor-settings');form.disabled=true;
            try{
                const response=await fetch('/api/repeater-statistics/neighbor-monitor',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},signal:AbortSignal.timeout(5000),body:JSON.stringify({public_key:key,enabled:$('neighbor-monitor-enabled').checked,interval_minutes:Number($('neighbor-monitor-interval').value)})}),data=await response.json();
                if(!response.ok||!data.ok)throw Error(data.error||ui("Could not save monitoring settings."));
                if(key===selected)await loadMonitoring(key,sequence);
            }catch(error){if(key===selected)$('neighbor-monitor-status').textContent=uiError(error.message);}
            finally{if(key===selected&&monitorKey===key)form.disabled=false;}
        });
        $('neighbor-monitor-recheck')?.addEventListener('click',async()=>{
            if(!monitorKey||monitorKey!==selected)return;const key=monitorKey;
            try{
                const response=await fetch('/api/repeater-statistics/neighbor-monitor',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},signal:AbortSignal.timeout(5000),body:JSON.stringify({operation:'recheck_protocol',public_key:key})}),data=await response.json();
                if(!response.ok||!data.ok)throw Error(data.error||ui("Could not request protocol recheck."));
                if(key===selected){await loadMonitoring(key,sequence);$('neighbor-monitor-status').textContent+=ui(" · Protocol will be checked at the next scheduled collection; the polling interval is unchanged.");}
            }catch(error){if(key===selected)$('neighbor-monitor-status').textContent=uiError(error.message);}
        });
        $('statistics-repeater').addEventListener('change',()=>{selected=$('statistics-repeater').value;clearView();load();});
        $('statistics-period')?.addEventListener('change',()=>{clearView();load();});
        $('statistics-refresh')?.addEventListener('click',load);
        $('statistics-regions-settings')?.addEventListener('toggle',async()=>{
            if(!$('statistics-regions-settings').open)return;
            try{const response=await fetch('/api/repeater-statistics/regions',{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal:AbortSignal.timeout(10000)}),data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||ui("Region settings unavailable."));$('statistics-region-names').value=data.regions.map(r=>r.name+' '+r.scope_key).join('\n');}
            catch(error){$('statistics-region-status').textContent=uiError(error.message);}
        });
        $('statistics-regions-save')?.addEventListener('click',async()=>{
            const button=$('statistics-regions-save');if(button.disabled)return;button.disabled=true;
            try{const regions=$('statistics-region-names').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean).map(line=>{const[name,scope_key,...extra]=line.split(/\s+/);if(extra.length)throw Error(ui("Use a name and optional key on each line."));return {name,scope_key};});
                const response=await fetch('/api/repeater-statistics/regions',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},body:JSON.stringify({regions}),signal:AbortSignal.timeout(10000)}),data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||ui("Region settings could not be saved."));$('statistics-region-status').textContent=ui("Region names saved locally. No radio commands were sent.");clearView();load();
            }catch(error){$('statistics-region-status').textContent=uiError(error.message);}finally{button.disabled=false;}
        });
        document.addEventListener('managed-repeater-added',()=>{if(section.open)load();});
        document.addEventListener('managed-repeater-removed',event=>{if(selected===event.detail)selected='';if(section.open)load();});
        document.addEventListener('visibilitychange',()=>document.hidden?stop():load());
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
