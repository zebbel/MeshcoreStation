/* Local status only: opening this panel never requests radio communication. */
(() => {
    const $=id=>document.getElementById('clock-sync-'+id);
    let attached=false,key='',config=null,sequence=0,controller=null,timer=null,dirty=false,busy=false;
    const states={disabled:'Disabled',scheduled:'Scheduled',checking:'Checking clock',writing:'Clock command in progress',verified:'Clock verified within tolerance',synchronized:'Synchronization verified',latency_uncertain:'Clock comparison limited by communication latency',ahead:'Repeater clock ahead — no backward adjustment',error:'Check failed',interrupted:'Check interrupted',verification_required:'Paused — manual clock verification required'};
    const stamp=value=>value==null?'Not recorded':window.meshcorestationFormatDate?.(value)||new Date(value*1000).toLocaleString();
    function render(value,running){
        config=value;
        $('summary').textContent=(value.enabled?'Enabled':'Disabled')+' · every '+value.interval_hours+' hours';
        if(!dirty){$('enabled').checked=!!value.enabled;$('interval').value=String(value.interval_hours);}
        $('save').disabled=busy||!key;
        $('state').textContent=(states[value.state]||value.state)+(value.enabled&&!running?' · Worker offline; saved schedule retained':'');
        $('result').textContent=value.last_result?(states[value.last_result.state]||value.last_result.state):'Not recorded';
        $('attempt').textContent=stamp(value.last_attempt);$('success').textContent=stamp(value.last_success);
        $('next').textContent=value.uncertain?'Paused until manually verified':value.enabled?stamp(value.next_due):'Not scheduled';
        $('offset').textContent=value.clock_offset==null?'Not measured':(value.clock_offset>0?'+':'')+Number(value.clock_offset).toFixed(1)+' seconds'+(value.last_result?.latency_allowance_seconds>1?' (includes communication latency)':'');
        $('error').textContent=value.error||value.last_result?.error||'None';
    }
    function schedule(){
        clearTimeout(timer);
        if(key&&$('disclosure').open&&document.getElementById('repeater-management-disclosure')?.open)
            timer=setTimeout(()=>load(false),10000);
    }
    async function load(reset=true){
        clearTimeout(timer);controller?.abort();controller=new AbortController();
        const seq=++sequence,selected=key,abort=controller;
        if(reset){dirty=false;config=null;$('save').disabled=true;$('message').textContent=selected?'Loading saved clock settings…':'Select a managed repeater.';}
        if(!selected){$('summary').textContent='Select a managed repeater';$('enabled').checked=false;$('interval').value='24';for(const name of ['state','attempt','result','success','next','offset','error'])$(name).textContent='Not recorded';return;}
        const timeout=setTimeout(()=>abort.abort(),8000);
        try{
            const response=await fetch('/api/repeater-clock-sync?public_key='+encodeURIComponent(selected),{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal:abort.signal});
            const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Clock settings unavailable.');
            if(seq!==sequence||selected!==key)return;
            render(data.config,data.running);if(reset)$('message').textContent='Settings and status are saved locally. Manual Sync clock remains available.';
        }catch(error){if(seq===sequence)$('message').textContent=error.name==='AbortError'?'Clock status request timed out. Background scheduling is independent.':error.message;}
        finally{clearTimeout(timeout);if(seq===sequence)schedule();}
    }
    async function save(){
        if(!config||!key||busy)return;
        const enabled=$('enabled').checked;
        let acknowledge=false;
        if(enabled&&config.uncertain){
            acknowledge=window.confirm('The previous clock-setting command has an uncertain outcome. Manually verify the repeater clock first. Have you verified it and want to resume scheduled synchronization?');
            if(!acknowledge)return;
        }
        controller?.abort();clearTimeout(timer);const seq=++sequence,selected=key,revision=config.revision;
        const abort=new AbortController();controller=abort;const timeout=setTimeout(()=>abort.abort(),8000);
        busy=true;$('save').disabled=true;$('message').textContent='Saving clock settings…';
        try{
            const response=await fetch('/api/repeater-clock-sync',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},signal:abort.signal,
                body:JSON.stringify({public_key:selected,enabled,interval_hours:Number($('interval').value),revision,acknowledge_uncertain:acknowledge})});
            const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Could not save clock settings.');
            if(seq!==sequence||selected!==key)return;
            dirty=false;render(data.config,data.running);$('message').textContent='Clock settings saved. No radio request was made by this page.';
        }catch(error){if(seq===sequence)$('message').textContent=error.name==='AbortError'?'Save outcome unavailable. Reload settings before saving again.':error.message;}
        finally{clearTimeout(timeout);busy=false;$('save').disabled=!config||!key;if(seq===sequence)schedule();}
    }
    function attach(){
        if(attached||!$('disclosure'))return;attached=true;
        const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.id='clock-sync-enabled';
        label.append(input,document.createTextNode('Enable automatic clock synchronization'));$('enable-host').append(label);
        input.addEventListener('change',()=>{dirty=true;});$('interval').addEventListener('change',()=>{dirty=true;});$('save').onclick=save;
        document.addEventListener('managed-repeater-selected',event=>{key=event.detail||'';load();});
        $('disclosure').addEventListener('toggle',()=>{if($('disclosure').open&&!busy)load(!dirty);else clearTimeout(timer);});
        document.getElementById('repeater-management-disclosure')?.addEventListener('toggle',()=>{if(document.getElementById('repeater-management-disclosure').open&&key&&!busy)load(!dirty);else clearTimeout(timer);});
        key=window.meshcorestationSelectedRepeater||'';if(key)load();
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
