/* Approximate standard 1S LiPo state of charge; this is not a fuel-gauge reading.
   The generic nonlinear curve is intentionally explicit for future calibration. */
window.MeshcoreStationBattery = (() => {
    const curve = [[3.0,0],[3.3,2],[3.5,5],[3.6,10],[3.7,20],[3.75,30],[3.8,40],[3.85,50],[3.9,60],[3.95,70],[4.0,80],[4.1,90],[4.2,100]];
    function percent(voltage) {
        if (!Number.isFinite(voltage) || voltage < 3.0 || voltage > 4.2) return null;
        for (let i=1;i<curve.length;i++) if (voltage<=curve[i][0]) {
            const [v0,p0]=curve[i-1],[v1,p1]=curve[i]; return Math.round(p0+(voltage-v0)/(v1-v0)*(p1-p0));
        }
        return 100;
    }
    function reading(voltage) {
        if (!Number.isFinite(voltage)) return 'No valid reading';
        const p=percent(voltage);
        return `${voltage.toFixed(2)} V · ${p === null ? 'outside 1S estimate range' : '≈' + p + '%'}`;
    }
    function chart(box, note, samples, zone, days, end) {
        box.replaceChildren(); note.textContent='';
        const good=samples.filter(p=>Number.isFinite(p.voltage));
        if(!good.length){box.textContent='No valid readings in this period. Select a repeater and request a reading in Battery history / settings.';return;}
        const ns='http://www.w3.org/2000/svg',w=940,h=290,left=70,right=24,top=20,bottom=48,low=3.0,high=4.2,start=end-days*86400;
        const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('role','img');svg.setAttribute('aria-label','Battery voltage, fixed scale 3.0 to 4.2 volts. Missing readings break the line.');
        const x=t=>left+(t-start)/(end-start)*(w-left-right),y=v=>top+(high-v)/(high-low)*(h-top-bottom);
        const date=t=>new Date(t*1000).toLocaleString(undefined,{timeZone:zone,dateStyle:'short',timeStyle:'short'});
        function shape(tag,attrs,text){const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;svg.append(n);return n;}
        for(let i=0;i<=6;i++){const v=low+i*0.2;shape('line',{x1:left,y1:y(v),x2:w-right,y2:y(v),class:'voltage-grid'});shape('text',{x:left-10,y:y(v)+4,'text-anchor':'end'},`${v.toFixed(1)} V`);}
        for(let i=0;i<=3;i++){const t=start+(end-start)*i/3;shape('text',{x:x(t),y:h-17,'text-anchor':i===0?'start':i===3?'end':'middle'},date(t));}
        let path='',previous=null;
        for(const p of samples){
            if(!Number.isFinite(p.voltage)||p.voltage<low||p.voltage>high){previous=null;continue;}
            const joined=previous&&p.sampled_at-previous.sampled_at<=1.5*Math.max(p.interval_seconds,previous.interval_seconds);
            path+=`${joined?'L':'M'}${x(p.sampled_at).toFixed(2)},${y(p.voltage).toFixed(2)} `;previous=p;
        }
        shape('path',{d:path,fill:'none',class:'voltage-line'});
        const stride=Math.max(1,Math.ceil(good.length/600));
        good.forEach((p,i)=>{if(i%stride&&i!==good.length-1)return;const outside=p.voltage<low||p.voltage>high;const dot=shape('circle',{cx:x(p.sampled_at),cy:y(Math.max(low,Math.min(high,p.voltage))),r:outside?5:3,class:outside?'voltage-outside':'voltage-dot'});const title=document.createElementNS(ns,'title');title.textContent=`${date(p.sampled_at)}: ${reading(p.voltage)}${outside?' (outside chart range)':''}`;dot.append(title);});
        box.append(svg);
        const outside=good.filter(p=>p.voltage<low||p.voltage>high).length;
        note.textContent=`Fixed 1S LiPo scale: 3.0–4.2 V · ${good.length} valid / ${samples.length} attempts · ${zone}. Gaps indicate failed readings or outages.${outside?' '+outside+' out-of-range reading(s), marked at the chart edge.':''} Percentages are approximate voltage-based estimates; charging, load and cell chemistry affect them.`;
    }
    return {percent,reading,chart};
})();
