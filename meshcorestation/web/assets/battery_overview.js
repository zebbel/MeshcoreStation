/* Main battery panel: reads saved history only, never requests additional radio traffic. */
(() => {
    let loading=false, attached=false, generation=0, lastData=null, activeKey='';
    const el=id=>document.getElementById(id);
    async function load(){
        if(!el('battery-overview-days')||!el('repeater-management-disclosure')?.open)return;
        if(document.hidden)return;
        const key=window.meshcorestationSelectedRepeater||'';
        if(loading && activeKey===key)return;
        activeKey=key;const id=++generation;
        if(!key){lastData=null;el('battery-overview-latest').textContent='Add a repeater to view its battery history.';el('battery-overview-chart').replaceChildren();el('battery-overview-note').textContent='';el('battery-overview-error').textContent='';return;}
        loading=true;
        try{
            const days=Number(el('battery-overview-days').value);
            const response=await fetch('/api/bot/voltage?days='+days+(key?'&public_key='+encodeURIComponent(key):''),{cache:'no-store',headers:{'X-Meshcore-Control':'1'}});
            const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||'Battery history unavailable.');
            if(id!==generation)return;
            const name=data.repeaters.find(r=>r.public_key===(key||data.config.public_key))?.name||data.config.public_key||'No repeater selected';
            const latest=data.latest;
            const date=stamp=>window.meshcorestationFormatDate(stamp,data.config.timezone,{seconds:false});
            el('battery-overview-latest').textContent=latest?`${name}: ${latest.voltage===null?'Reading failed':window.MeshcoreStationBattery.reading(latest.voltage)} · ${date(latest.sampled_at)}${latest.error?' · '+latest.error:''}`:name+' · No readings yet';
            lastData={data,days};
            drawChart();
            el('battery-overview-error').textContent='';
        }catch(error){if(id!==generation)return;el('battery-overview-error').textContent=error.message+' Displayed readings may be stale.';}
        finally{if(id===generation)loading=false;}
    }
    function drawChart(){
        if(!lastData||!el('battery-chart-disclosure')?.open)return;
        const {data,days}=lastData;
        window.MeshcoreStationBattery.chart(el('battery-overview-chart'),el('battery-overview-note'),data.samples,data.config.timezone,days,data.server_time);
    }
    function attach(){
        const panel=el('battery-overview');if(!panel||attached)return;attached=true;
        panel.innerHTML='<p id="battery-overview-latest" class="battery-reading">Loading saved battery history…</p><p id="battery-overview-error" role="status"></p><details id="battery-chart-disclosure"><summary>Battery chart</summary><label>Chart period <select id="battery-overview-days"><option value="1" selected>24 hours</option><option value="7">7 days</option><option value="30">30 days</option></select></label><div id="battery-overview-chart" class="battery-chart"></div><p id="battery-overview-note" class="muted"></p></details>';
        el('battery-chart-disclosure').addEventListener('toggle',drawChart);
        el('battery-overview-days').addEventListener('change',load);load();setInterval(load,15000);
    }
    document.addEventListener('managed-repeater-selected',()=>{lastData=null;if(el('battery-overview-latest')){el('battery-overview-latest').textContent='Loading selected repeater…';el('battery-overview-chart').replaceChildren();}load();});
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
