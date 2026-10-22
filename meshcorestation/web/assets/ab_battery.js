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
    const selections=new WeakMap();
    function seriesChart(box,note,samples,zone,days,end,field) {
        box.replaceChildren();note.textContent='';
        const temperature=field==='temperature',unit=temperature?'°C':'V',decimals=temperature?1:2;
        const value=p=>p[field],format=p=>`${value(p).toFixed(decimals)} ${unit}`;
        const start=end-days*86400;
        const points=samples.filter(p=>Number.isFinite(p.sampled_at)&&p.sampled_at>=start&&p.sampled_at<=end)
            .sort((a,b)=>a.sampled_at-b.sampled_at);
        const good=points.filter(p=>Number.isFinite(value(p)));
        if(!good.length){box.textContent=temperature?'No temperature readings in this period. Check the temperature LPP channel in Telemetry history / settings.':'No valid voltage readings in this period. Request a reading in Telemetry history / settings.';selections.delete(box);return;}
        const ns='http://www.w3.org/2000/svg',w=940,h=290,left=70,right=24,top=20,bottom=48;
        let low=3.0,high=4.2;
        if(temperature){
            const values=good.map(value),min=Math.min(...values),max=Math.max(...values),padding=Math.max(1,(max-min)*0.1);
            low=Math.floor(min-padding);high=Math.ceil(max+padding);
        }
        const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
        svg.setAttribute('role','img');svg.setAttribute('tabindex','0');svg.classList.add('telemetry-chart-svg');
        const label=temperature?'Repeater temperature in Celsius':'Battery voltage, fixed scale 3.0 to 4.2 volts';
        svg.setAttribute('aria-label',label+'. Click or tap to select a measurement.');
        const x=t=>left+(t-start)/(end-start)*(w-left-right),y=v=>top+(high-v)/(high-low)*(h-top-bottom);
        const bounded=v=>Math.max(low,Math.min(high,v));
        const date=t=>window.meshcorestationFormatDate(t,zone,{seconds:false});
        function shape(tag,attrs,text){const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;svg.append(n);return n;}
        for(let i=0;i<=6;i++){const v=low+i*(high-low)/6;shape('line',{x1:left,y1:y(v),x2:w-right,y2:y(v),class:'voltage-grid'});shape('text',{x:left-10,y:y(v)+4,'text-anchor':'end'},`${v.toFixed(1)} ${unit}`);}
        for(let i=0;i<=3;i++){const t=start+(end-start)*i/3;shape('text',{x:x(t),y:h-17,'text-anchor':i===0?'start':i===3?'end':'middle'},date(t));}
        let path='',previous=null;
        for(const p of points){
            if(!Number.isFinite(value(p))||value(p)<low||value(p)>high){previous=null;continue;}
            const joined=previous&&p.sampled_at-previous.sampled_at<=1.5*Math.max(p.interval_seconds||1800,previous.interval_seconds||1800);
            path+=`${joined?'L':'M'}${x(p.sampled_at).toFixed(2)},${y(value(p)).toFixed(2)} `;previous=p;
        }
        shape('path',{d:path,fill:'none',class:'voltage-line'});
        const stride=Math.max(1,Math.ceil(good.length/600));
        good.forEach((p,i)=>{if(i%stride&&i!==good.length-1)return;const outside=value(p)<low||value(p)>high;
            shape('circle',{cx:x(p.sampled_at),cy:y(bounded(value(p))),r:outside?5:3,class:outside?'voltage-outside':'voltage-dot'});
        });
        let highlight,text;
        function select(p){
            highlight?.remove();text?.remove();
            highlight=shape('circle',{cx:x(p.sampled_at),cy:y(bounded(value(p))),r:7,class:'telemetry-selected-point'});
            text=shape('text',{x:Math.max(left+65,Math.min(w-right-65,x(p.sampled_at))),
                y:Math.max(top+20,Math.min(h-bottom-10,y(bounded(value(p)))-16)),
                'text-anchor':'middle',class:'telemetry-selected-value'},format(p));
            selections.set(box,{at:p.sampled_at,value:value(p)});
            svg.setAttribute('aria-label',label+'. Selected '+format(p));
        }
        function pick(event){
            if(event.button!=null&&event.button!==0)return;
            const touch=event.touches?.[0]||event,rect=svg.getBoundingClientRect();
            const px=(touch.clientX-rect.left)*w/(rect.width||w),py=(touch.clientY-rect.top)*h/(rect.height||h);
            let nearest=good[0],distance=Infinity;
            // Search all recorded values, including dots omitted for rendering speed.
            for(const p of good){const d=(x(p.sampled_at)-px)**2+(y(bounded(value(p)))-py)**2;
                if(d<distance){nearest=p;distance=d;}}
            select(nearest);
        }
        svg.addEventListener('click',pick);svg.addEventListener('pointerdown',pick);
        svg.addEventListener('touchstart',pick,{passive:true});
        svg.addEventListener('keydown',event=>{
            if(!['ArrowLeft','ArrowRight','Enter',' '].includes(event.key))return;event.preventDefault();
            const selected=selections.get(box),i=good.findIndex(p=>p.sampled_at===selected?.at);
            select(good[i<0?good.length-1:Math.max(0,Math.min(good.length-1,i+(event.key==='ArrowLeft'?-1:event.key==='ArrowRight'?1:0)))]);
        });
        box.append(svg);
        const saved=selections.get(box),point=good.find(p=>p.sampled_at===saved?.at&&value(p)===saved?.value);
        if(point)select(point);else selections.delete(box);
        const outside=good.filter(p=>value(p)<low||value(p)>high).length;
        note.textContent=temperature?`${good.length} temperature readings · °C · ${zone}. Missing readings break the line.`:
            `Fixed 1S LiPo scale: 3.0–4.2 V · ${good.length} valid / ${points.length} attempts · ${zone}. Gaps indicate failed readings or outages.${outside?' '+outside+' out-of-range reading(s), marked at the chart edge.':''} Percentages are approximate voltage-based estimates; charging, load and cell chemistry affect them.`;
    }
    function chart(box,note,samples,zone,days,end){seriesChart(box,note,samples,zone,days,end,'voltage');}
    function temperatureChart(box,note,samples,zone,days,end){seriesChart(box,note,samples,zone,days,end,'temperature');}
    return {percent,reading,chart,temperatureChart};
})();
