/* Independent view only: membership and continuous collection belong to the server. */
(() => {
    const $ = id => document.getElementById(id);
    let attached=false, selected='', sequence=0;
    const requests=new Set();
    function stop(){sequence++;for(const request of requests)request.abort();requests.clear();}
    async function requestJSON(url,timeout,kind){
        const controller=new AbortController();requests.add(controller);let timedOut=false;
        const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeout);
        try{
            const response=await fetch(url,{cache:'no-store',signal:controller.signal});
            let value;try{value=await response.json();}catch{throw Error('The '+kind+' response was unreadable. Existing history is preserved.');}
            if(!response.ok||!value.ok){
                const error=Error(value.error||'The '+kind+' request failed.');error.code=value.error_code;error.status=response.status;throw error;
            }
            return value;
        }catch(error){
            if(timedOut){const timeoutError=Error(kind==='recording status'?'Recording-status request timed out in the browser (5 seconds).':'Saved-statistics request timed out in the browser (10 seconds); recording status remains available.');timeoutError.code='BROWSER_TIMEOUT';throw timeoutError;}
            throw error;
        }finally{clearTimeout(timer);requests.delete(controller);}
    }
    async function load(){
        const section=$('repeater-statistics-disclosure');if(!section?.open||document.hidden)return;
        stop();const ticket=sequence;
        window.MeshcoreStationStatisticsVisuals?.stale?.();
        const progress=$('statistics-view-status');if(progress){progress.textContent='Loading saved observations… Recording continues independently.';progress.setAttribute('aria-busy','true');}
        if($('statistics-view-error'))$('statistics-view-error').textContent='';
        let data;
        try{
            data=await requestJSON('/api/repeater-statistics/status'+(selected?'?public_key='+encodeURIComponent(selected):''),5000,'recording status');
            if(ticket!==sequence||!section.open)return;
            window.MeshcoreStationRepeaterNames?.ingest(data.repeaters);
            const picker=$('statistics-repeater');picker.replaceChildren();
            for(const repeater of data.repeaters){
                const option=new Option(window.MeshcoreStationRepeaterNames?.label(repeater.public_key)||repeater.name||`Unknown Repeater (${repeater.public_key.slice(0,8)}…)`,repeater.public_key);
                option.title=repeater.public_key;option.dataset.repeaterKey=repeater.public_key;picker.add(option);
            }
            selected=data.selected;picker.value=selected;picker.disabled=!data.repeaters.length;
            if(!selected){picker.add(new Option('No managed repeaters',''));$('statistics-status').textContent='Add a repeater in Repeater Management to begin passive recording.';}
            else{
                const health=data.health,state=!health.running?'Collector stopped':!health.connected?'Companion disconnected; saved history remains available':'Recording passive Companion observations';
                const count=data.observation_count===null?'Saved count unavailable':`${data.observation_count} saved observations (all time)`;
                const last=data.last_recorded_at?(window.meshcorestationFormatDate?.(data.last_recorded_at)||new Date(data.last_recorded_at*1000).toLocaleString('en-GB')):'No observations recorded yet';
                $('statistics-status').textContent=`${state}. ${count}. Last recorded: ${last}.`;
            }
            const health=data.health;
            $('statistics-error').textContent=[data.error,health.error,health.repeater_error,health.dropped?`${health.dropped} observations or repeater writes dropped this session; recording is incomplete.`:'',health.invalid?`${health.invalid} malformed/unsupported packet events skipped this session.`:''].filter(Boolean).join(' ');
        }catch(error){
            if(ticket!==sequence||!section.open)return;
            if(error.status===400)selected='';
            $('statistics-error').textContent=error.message;
            if($('statistics-status').textContent&&!$('statistics-status').textContent.startsWith('Last available status'))$('statistics-status').textContent='Last available status — '+$('statistics-status').textContent;
            if(progress){progress.textContent='Recording status unavailable. Refresh to try again.';progress.setAttribute('aria-busy','false');}
            return;
        }
        try{
            if($('statistics-hourly')){
                const params=new URLSearchParams({days:$('statistics-period').value||'1'});if(selected)params.set('public_key',selected);
                // A fresh independent budget starts after status has been rendered.
                const view=await requestJSON('/api/repeater-statistics/view?'+params,10000,'saved statistics');
                if(ticket!==sequence||!section.open)return;
                if(view.selected!==selected)throw Error('Managed repeater selection changed. Refresh the saved view.');
                window.MeshcoreStationStatisticsVisuals?.render(view);
                if(progress)progress.textContent='Saved observations loaded. Refresh this view to see newer records; no radio requests are made.';
            }
        }catch(error){
            if(ticket!==sequence||!section.open)return;
            const category=error.code==='QUERY_TIMEOUT'?'Server query timeout: ':error.code==='DATABASE_BUSY'?'Database busy: ':error.code==='DATABASE_ERROR'?'Database error: ':error.code==='STATISTICS_BUSY'?'Statistics calculation busy: ':'';
            ($('statistics-view-error')||$('statistics-error')).textContent=category+error.message;
            if(progress)progress.textContent='Statistics could not be refreshed. Recording status above remains available; faded charts are an older snapshot.';
        }finally{if(ticket===sequence&&progress)progress.setAttribute('aria-busy','false');}
    }
    function attach(){
        const section=$('repeater-statistics-disclosure');if(attached||!section)return;attached=true;
        section.addEventListener('toggle',()=>{if(section.open)load();else{stop();window.MeshcoreStationStatisticsVisuals?.dispose();}});
        function clearView(){window.MeshcoreStationStatisticsVisuals?.dispose();for(const id of ['statistics-hourly','statistics-hops','statistics-regions','statistics-coverage','statistics-map-notes','statistics-missing-coordinates','statistics-ambiguous'])$(id)?.replaceChildren();}
        $('statistics-repeater').addEventListener('change',()=>{selected=$('statistics-repeater').value;clearView();load();});
        $('statistics-period')?.addEventListener('change',()=>{clearView();load();});
        $('statistics-refresh')?.addEventListener('click',load);
        $('statistics-regions-settings')?.addEventListener('toggle',async()=>{
            if(!$('statistics-regions-settings').open)return;
            try{const response=await fetch('/api/repeater-statistics/regions',{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal:AbortSignal.timeout(10000)}),data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Region settings unavailable.');$('statistics-region-names').value=data.regions.map(r=>r.name+' '+r.scope_key).join('\n');}
            catch(error){$('statistics-region-status').textContent=error.message;}
        });
        $('statistics-regions-save')?.addEventListener('click',async()=>{
            const button=$('statistics-regions-save');if(button.disabled)return;button.disabled=true;
            try{const regions=$('statistics-region-names').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean).map(line=>{const[name,scope_key,...extra]=line.split(/\s+/);if(extra.length)throw Error('Use a name and optional key on each line.');return {name,scope_key};});
                const response=await fetch('/api/repeater-statistics/regions',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},body:JSON.stringify({regions}),signal:AbortSignal.timeout(10000)}),data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Region settings could not be saved.');$('statistics-region-status').textContent='Region names saved locally. No radio commands were sent.';clearView();load();
            }catch(error){$('statistics-region-status').textContent=error.message;}finally{button.disabled=false;}
        });
        document.addEventListener('managed-repeater-added',()=>{if(section.open)load();});
        document.addEventListener('managed-repeater-removed',event=>{if(selected===event.detail)selected='';if(section.open)load();});
        document.addEventListener('visibilitychange',()=>document.hidden?stop():load());
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
