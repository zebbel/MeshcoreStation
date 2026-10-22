(() => {
    let attached=false;
    function attach(){
        const dialog=document.getElementById('companion-dialog');if(!dialog||attached)return;attached=true;
        const panel=document.createElement('section');panel.id='display-settings';panel.className='companion-section';panel.style.marginTop='20px';
        panel.innerHTML='<h3>Date and time display</h3><p class="muted">Applies throughout MeshcoreStation. Timezones and report schedules are configured separately.</p><form><div class="companion-fields"><label>Date format<select id="display-date"><option value="german">German · DD.MM.YYYY</option><option value="iso">ISO · YYYY-MM-DD</option><option value="us">US · MM/DD/YYYY</option></select></label><label>Clock<select id="display-hours"><option value="24">24 hours</option><option value="12">12 hours · AM/PM</option></select></label></div><p class="display-preview"></p><button type="submit">Save and reload</button><p class="display-message" role="status"></p></form>';
        (dialog.querySelector('.dialog-body')||dialog).append(panel);
        const date=panel.querySelector('#display-date'),hours=panel.querySelector('#display-hours'),preview=panel.querySelector('.display-preview'),message=panel.querySelector('.display-message');
        date.value=window.meshcorestationDisplaySettings.date_format;hours.value=window.meshcorestationDisplaySettings.hour_format;
        const sample=()=>{const days={german:'22.10.2026',iso:'2026-10-22',us:'10/22/2026'};preview.textContent='Example: '+days[date.value]+' '+(hours.value==='12'?'04:30 PM':'16:30');};
        panel.addEventListener('change',sample);sample();
        panel.querySelector('form').onsubmit=async event=>{
            event.preventDefault();const button=panel.querySelector('button');button.disabled=true;
            try{const res=await fetch('/api/display-settings',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},body:JSON.stringify({date_format:date.value,hour_format:hours.value})});const data=await res.json();if(!res.ok||!data.ok)throw Error(data.error||'Could not save display settings.');location.reload();}
            catch(error){message.textContent=error.message;button.disabled=false;}
        };
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
