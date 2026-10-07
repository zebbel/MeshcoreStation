/* Main battery panel: reads saved history only, never requests additional radio traffic. */
(() => {
    let loading=false, attached=false;
    const el=id=>document.getElementById(id);
    async function load(){
        if(loading||!el('battery-overview-days'))return;loading=true;
        try{
            const days=Number(el('battery-overview-days').value);
            const response=await fetch('/api/bot/voltage?days='+days,{cache:'no-store',headers:{'X-Meshcore-Control':'1'}});
            const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||'Battery history unavailable.');
            const name=data.repeaters.find(r=>r.public_key===data.config.public_key)?.name||data.config.public_key||'No repeater selected';
            const latest=data.latest;
            const date=stamp=>new Date(stamp*1000).toLocaleString(undefined,{timeZone:data.config.timezone,dateStyle:'short',timeStyle:'short'});
            el('battery-overview-latest').textContent=latest?`${name}: ${latest.voltage===null?'Reading failed':window.MeshcoreStationBattery.reading(latest.voltage)} · ${date(latest.sampled_at)}${latest.error?' · '+latest.error:''}`:name+' · No readings yet';
            window.MeshcoreStationBattery.chart(el('battery-overview-chart'),el('battery-overview-note'),data.samples,data.config.timezone,days,data.server_time);
            el('battery-overview-error').textContent='';
        }catch(error){el('battery-overview-error').textContent=error.message+' Displayed readings may be stale.';}
        finally{loading=false;}
    }
    function attach(){
        const panel=el('battery-overview');if(!panel||attached)return;attached=true;
        panel.innerHTML='<p id="battery-overview-latest" class="battery-reading">Loading saved battery history…</p><p id="battery-overview-error" role="status"></p><details id="battery-chart-disclosure"><summary>Battery chart</summary><label>Chart period <select id="battery-overview-days"><option value="1" selected>24 hours</option><option value="7">7 days</option><option value="30">30 days</option></select></label><div id="battery-overview-chart" class="battery-chart"></div><p id="battery-overview-note" class="muted"></p></details>';
        el('battery-overview-days').addEventListener('change',load);load();setInterval(load,15000);
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
