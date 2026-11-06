/* Status polling is local only. Closing the UI never revokes a server-side read. */
(() => {
    const $=id=>document.getElementById(id),button=()=>$('neighbor-monitor-read-now'),message=()=>$('neighbor-monitor-read-status');
    const active=job=>job&&['queued','running'].includes(job.state);
    let key='',generation=0,timer=null,controller=null,attached=false,pendingJob=false,failures=0;
    let watchedJob='',refreshedJob='';
    const visible=()=>$('repeater-statistics-disclosure')?.open&&!document.hidden;
    function stop(){generation++;clearTimeout(timer);controller?.abort();key='';pendingJob=false;failures=0;watchedJob='';if(button())button().disabled=true;}
    function schedule(ticket){clearTimeout(timer);if(ticket===generation&&visible())timer=setTimeout(()=>status(ticket),1500);}
    async function request(options={}){
        controller?.abort();controller=new AbortController();const abort=controller,timeout=setTimeout(()=>abort.abort(),5000);
        try{
            const response=await fetch('/api/repeater-statistics/read-now'+(options.method?'':'?public_key='+encodeURIComponent(key)),{
                cache:'no-store',signal:abort.signal,headers:{'X-Meshcore-Control':'1',...(options.method?{'Content-Type':'application/json'}:{})},...options});
            const data=await response.json();
            if(!response.ok&&response.status!==409)throw Error(data.error||'Manual neighbor SNR read unavailable.');
            return data;
        }finally{clearTimeout(timeout);}
    }
    function render(data,ticket){
        if(ticket!==generation||!key||!button())return;
        const job=data.job,busy=!!data.busy;pendingJob=!!active(job)||busy;failures=0;
        button().disabled=!data.ready||busy||!!active(job);
        if(active(job)){
            watchedJob=job.job_id;
            message().textContent='Reading neighbor SNR… '+(job.progress||'Waiting for collection.')+' Records retrieved: '+job.records+'.';
            schedule(ticket);return;
        }
        if(job){
            const labels={complete:'Read complete',partial:'Partial read',error:'Read failed',cancelled:'Read cancelled',interrupted:'Read interrupted'};
            message().textContent=(labels[job.state]||job.state)+' · Records retrieved: '+job.records+'.'+(job.error?' '+job.error:'')+(job.protocol==='averaged'?' Only completed firmware windows are read.':'');
            if(watchedJob===job.job_id&&refreshedJob!==job.job_id){
                refreshedJob=job.job_id;
                if(visible()&&$('statistics-repeater')?.value===key){
                    if(window.MeshcoreStationRefreshSavedSnr)window.MeshcoreStationRefreshSavedSnr();
                    else $('statistics-refresh')?.click();
                }
            }
        }else message().textContent=data.ready?'Read once without changing automatic monitoring or its schedule.':'Companion disconnected or neighbor collector offline.';
        if(busy){message().textContent+=' Another manual SNR read is pending.';schedule(ticket);}
    }
    async function status(ticket){
        if(ticket!==generation||!key||!visible())return;
        try{const data=await request();render(data,ticket);}
        catch(error){if(ticket===generation){message().textContent=error.name==='AbortError'?'Manual read status timed out. Server-side collection may still be running.':error.message;button().disabled=pendingJob;if(pendingJob&&++failures<3)schedule(ticket);}}
    }
    function load(selected){stop();key=selected||'';if(!key)return;attach();if(button())status(generation);}
    function attach(){
        if(attached||!button())return;attached=true;
        button().addEventListener('click',async()=>{
            if(!key||!visible()||$('statistics-repeater')?.value!==key)return;
            clearTimeout(timer);pendingJob=true;button().disabled=true;message().textContent='Reading neighbor SNR…';const ticket=generation,selected=key;
            try{
                const data=await request({method:'POST',body:JSON.stringify({public_key:selected})});
                if(ticket!==generation)return;
                if(active(data.job)){watchedJob=data.job.job_id;render(data,ticket);}
                else if(!data.ok){message().textContent=data.error||'Another read is pending.';render({...data,job:null},ticket);}
                else render(data,ticket);
            }catch(error){if(ticket===generation){message().textContent=(error.name==='AbortError'?'Read submission status unavailable; checking the saved job.':error.message);await status(ticket);}}
        });
    }
    window.MeshcoreStationNeighborReadNow={load,stop};
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
