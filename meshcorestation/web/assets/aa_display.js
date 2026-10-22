/* One explicit date/clock policy across dashboard, maps and embedded tools. */
(() => {
    const defaults={date_format:'german',hour_format:'24',timezone:'Europe/Berlin'};
    let preferences;
    try { preferences=JSON.parse(document.querySelector('meta[name="meshcorestation-display"]')?.content||'null'); } catch (_) {}
    const settings={...defaults,...preferences};
    window.meshcorestationDisplaySettings=settings;
    const formats=new Map();
    window.meshcorestationFormatDate=(value,zone=settings.timezone,{timeOnly=false,dateOnly=false,seconds=true}={})=>{
        if(value==null)return 'Not recorded';
        const date=value instanceof Date?value:new Date(Number(value)*1000);
        if(!Number.isFinite(date.getTime()))return 'Not recorded';
        const cache=zone+'|'+seconds+'|'+settings.hour_format;
        if(!formats.has(cache))formats.set(cache,new Intl.DateTimeFormat('en-US',{
            timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',
            ...(seconds?{second:'2-digit'}:{}),hourCycle:settings.hour_format==='12'?'h12':'h23'}));
        const p=Object.fromEntries(formats.get(cache).formatToParts(date).map(part=>[part.type,part.value]));
        const day=settings.date_format==='iso'?`${p.year}-${p.month}-${p.day}`:settings.date_format==='us'?`${p.month}/${p.day}/${p.year}`:`${p.day}.${p.month}.${p.year}`;
        const clock=`${p.hour}:${p.minute}${seconds?':'+p.second:''}${settings.hour_format==='12'?' '+p.dayPeriod:''}`;
        return timeOnly?clock:dateOnly?day:day+' '+clock;
    };
})();
