/* Saved passive observations only; native chart SVGs never style Leaflet SVGs. */
(() => {
    const {t: ui} = window.MeshcoreStationI18n || {
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`))
    };
    const $=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg';
    let map=null,resize=null,chartResize=null,generation=0,lastData=null,mapPoints=[],mapNeedsFit=false,regionalAll=false;
    const text=(tag,value,cls)=>{const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;};
    const stamp=value=>window.meshcorestationFormatDate?.(value)||new Date(value*1000).toLocaleString('en-GB');
    const name=r=>window.MeshcoreStationRepeaterNames?.label(r.public_key)||r.name||ui("Unknown Repeater ({0}…)", r.public_key.slice(0,8));
    function svg(tag,attributes={},content){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attributes))e.setAttribute(k,v);if(content!==undefined)e.textContent=content;return e;}
    function chart(host,label,height=260){const s=svg('svg',{viewBox:`0 0 900 ${height}`,role:'img','aria-label':label});host.replaceChildren(s);return s;}
    function legend(host,unidentified=true){host.append(text('p',ui("Unique packets · blue | Repeated receptions · orange")+(unidentified?ui(" | Unidentified payloads · gray"):''),'statistics-chart-legend'));}
    function exactCounts(host,rows,labelOf,{percent=false,coverage=false}={}){
        const details=document.createElement('details');details.append(text('summary',coverage?ui("Show exact hourly counts"):ui("Show exact counts")));
        let populated=false;
        details.addEventListener('toggle',()=>{
            if(!details.open||populated)return;populated=true;
            const scroll=text('div','','statistics-table-scroll'),table=document.createElement('table'),head=document.createElement('tr');
            for(const v of [ui("Category"),ui("Receptions"),ui("Unique"),ui("Repeated"),ui("Unidentified"),...(coverage?[ui("Coverage")]:[]),...(percent?[ui("Share")]:[])])head.append(text('th',v));table.append(head);
            for(const r of rows){const row=document.createElement('tr');for(const v of [labelOf(r),r.receptions??ui("Unknown"),r.unique_packets??ui("Unknown"),r.repeated??ui("Unknown"),r.unidentified??ui("Unknown"),...(coverage?[r.complete?ui("Complete"):ui("Incomplete / unknown")]:[]),...(percent?[r.percentage.toFixed(1)+'%']:[])])row.append(text('td',v));table.append(row);}
            scroll.append(table);details.append(scroll);
        });host.append(details);
    }
    function scale(max){
        const raw=Math.max(1,max)/4,power=10**Math.floor(Math.log10(raw));
        const step=Math.max(1,[1,2,5,10].map(n=>n*power).find(n=>n>=raw));
        return {step,top:Math.max(1,Math.ceil(max/step))*step};
    }
    function columns(host,label,rows,max,{key,minimum=28,latest=false}={}){
        const old=host.querySelector('.statistics-plot-scroll'),saved=old?.dataset.view===key?old.scrollLeft:null;
        const viewport=Math.max(240,(host.clientWidth||900)-64),width=Math.max(viewport,rows.length*minimum),height=300,base=220,plot=184;
        const {step,top}=scale(max),y=value=>base-value/top*plot;
        host.replaceChildren();const frame=text('div','','statistics-vertical-frame'),axis=svg('svg',{viewBox:'0 0 64 300',class:'statistics-y-axis','aria-hidden':'true'}),scroll=text('div','','statistics-plot-scroll');
        scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',label+ui("; scroll horizontally to inspect every interval"));scroll.dataset.view=key;
        const s=svg('svg',{viewBox:`0 0 ${width} ${height}`,class:'statistics-column-chart',role:'img','aria-label':label});s.style.width=width+'px';
        for(let value=0;value<=top;value+=step){axis.append(svg('text',{x:59,y:y(value)+4,'text-anchor':'end'},value));s.append(svg('line',{x1:0,y1:y(value),x2:width,y2:y(value),class:'statistics-grid'}));}
        axis.append(svg('text',{transform:'translate(8 135) rotate(-90)','text-anchor':'middle',class:'statistics-axis-title'},ui("Observed receptions")));
        scroll.append(s);frame.append(axis,scroll);host.append(frame);
        const hover=text('p',ui("Hover, focus or tap a column to inspect counts."),'statistics-hover-value');hover.setAttribute('role','status');hover.setAttribute('aria-live','polite');host.append(hover);
        const spacing=width/Math.max(1,rows.length);
        function interactive(node,value){node.setAttribute('tabindex','0');node.setAttribute('aria-label',value);node.append(svg('title',{},value));for(const event of ['pointerenter','focus','click'])node.addEventListener(event,()=>{hover.textContent=value;});}
        if(width>viewport+1){const controls=text('div','','statistics-chart-navigation');controls.append(text('span',ui("Scroll horizontally to inspect every interval."),'muted'));
            for(const[title,left]of [[ui("Start"),0],[latest?ui("Latest hours"):ui("Highest hop counts"),width]]){const button=text('button',title,'secondary');button.type='button';button.addEventListener('click',()=>{scroll.scrollLeft=left;});controls.append(button);}host.append(controls);
        }
        requestAnimationFrame(()=>{if(scroll.isConnected)scroll.scrollLeft=saved??(latest?width:0);});
        return {s,y,base,plot,width,spacing,interactive};
    }
    function countDescription(r){return ui("{0} receptions; {1} unique; {2} repeated; {3} unidentified", r.receptions??ui("Unknown"), r.unique_packets??ui("Unknown"), r.repeated??ui("Unknown"), r.unidentified??ui("Unknown"));}
    function hourly(data){
        const host=$('statistics-hourly');if(!host)return;const rows=data.hourly;
        const max=Math.max(1,...rows.map(r=>Math.max(r.unique_packets||0,r.repeated||0)));
        const f=columns(host,ui("Observed text messages per hour"),rows,max,{key:data.selected+'|'+data.days,minimum:24,latest:true});
        const gapId='statistics-hourly-gap',defs=svg('defs'),pattern=svg('pattern',{id:gapId,width:8,height:8,patternUnits:'userSpaceOnUse'});pattern.append(svg('path',{d:'M-2 2L2-2M0 8L8 0M6 10L10 6',class:'statistics-gap-hatch'}));defs.append(pattern);f.s.prepend(defs);
        rows.forEach((r,i)=>{
            const left=i*f.spacing,unknown=r.unique_packets==null||r.repeated==null,coverage=r.complete?ui("Complete recording coverage"):ui("Incomplete / unknown coverage; observed counts are lower bounds");
            const group=svg('g',{class:'statistics-hour','data-at':r.at});
            if(unknown){const gap=svg('rect',{x:left,y:f.base-f.plot,width:f.spacing,height:f.plot,fill:`url(#${gapId})`,class:'statistics-coverage-gap'});f.interactive(gap,ui("{0} · Unknown traffic; collection coverage is not verified. This is not a zero.", stamp(r.at)));group.append(gap);}
            else{
                const barWidth=Math.min(20,Math.max(3,(f.spacing-6)/2)),center=left+f.spacing/2;
                for(const[field,color,offset]of[['unique_packets','#2563eb',-barWidth-1],['repeated','#c75c0d',1]]){
                    const value=r[field],bar=svg('rect',{x:center+offset,y:f.y(value),width:barWidth,height:f.base-f.y(value),fill:color,stroke:'none','stroke-width':0,class:'statistics-hour-bar'+(r.complete?'':' statistics-incomplete'),'data-series':field,'data-value':value});
                    f.interactive(bar,`${stamp(r.at)} · ${field==='unique_packets'?ui("Unique packets"):ui("Repeated receptions")}: ${value}. ${countDescription(r)}. ${coverage}.`);group.append(bar);
                }
                if(r.receptions===0&&r.complete){const zero=svg('text',{x:center,y:f.base-5,'text-anchor':'middle',class:'statistics-confirmed-zero'},'0');f.interactive(zero,ui("{0} · 0 text receptions during a fully recorded interval.", stamp(r.at)));group.append(zero);}
                if(r.receptions>0&&!r.unique_packets&&!r.repeated){const other=svg('text',{x:center,y:f.base-5,'text-anchor':'middle',class:'statistics-unplotted'},'?');f.interactive(other,ui("{0} · {1} unidentified receptions retained in the exact-count table, not plotted as unique or repeated.", stamp(r.at), r.unidentified));group.append(other);}
            }
            f.s.append(group);
            const interval=Math.max(1,Math.ceil(145/f.spacing));
            if(i%interval===0||i===rows.length-1){const last=i===rows.length-1;if(last&&i%interval<interval/2&&i!==0)return;const tick=svg('text',{x:left+f.spacing/2,y:244,'text-anchor':i===0?'start':last?'end':'middle',class:'statistics-time-tick'}),parts=stamp(r.at).split(' ');tick.append(svg('tspan',{x:left+f.spacing/2},parts.shift()),svg('tspan',{x:left+f.spacing/2,dy:17},parts.join(' ')));f.s.append(tick);}
        });
        f.s.append(svg('text',{x:f.width/2,y:289,'text-anchor':'middle',class:'statistics-axis-title'},ui("Hour · ")+(window.meshcorestationDisplaySettings?.timezone||ui("dashboard time zone"))));
        legend(host,false);host.append(text('p',ui("Group and direct-text payloads on confidently attributed flood paths. Incomplete counts are lower bounds (see tooltips); hatched gaps are unknown, not zero traffic. Unidentified receptions remain in the table. Unique/repeated counts are calculated within each hour."),'muted'));
        if(!rows.some(r=>r.receptions!=null))host.append(text('p',ui("No confirmed text observations or verified collection coverage in this period."),'statistics-empty'));
        exactCounts(host,rows,r=>stamp(r.at),{coverage:true});
    }
    function hopColumns(data){
        const host=$('statistics-hops');if(!host)return;const rows=[...data.hops].sort((a,b)=>a.hop_count-b.hop_count);
        if(!rows.length){host.replaceChildren(text('p',ui("No confidently attributed observations in this period."),'statistics-empty'));return;}
        const max=Math.max(1,...rows.map(r=>Math.max(r.unique_packets,r.repeated)));
        const f=columns(host,ui("Observed total route hop count"),rows,max,{key:data.selected+'|'+data.days,minimum:72});
        rows.forEach((r,i)=>{const center=(i+.5)*f.spacing,width=Math.min(30,(f.spacing-8)/2),description=ui("{0} {1}: {2}. Columns show identified receptions; unidentified counts remain in the table.", r.hop_count, r.hop_count===1?'hop':'hops', countDescription(r));
            for(const[field,color,offset]of[['unique_packets','#2563eb',-width-1],['repeated','#c75c0d',1]]){const value=r[field],bar=svg('rect',{x:center+offset,y:f.y(value),width,height:f.base-f.y(value),fill:color,class:'statistics-hop-bar','data-hop':r.hop_count,'data-series':field,'data-value':value});f.interactive(bar,description);f.s.append(bar);}
            f.s.append(svg('text',{x:center,y:246,'text-anchor':'middle',class:'statistics-hop-tick','data-hop':r.hop_count},r.hop_count));
        });f.s.append(svg('text',{x:f.width/2,y:282,'text-anchor':'middle',class:'statistics-axis-title'},ui("Total route hop count")));
        legend(host,false);host.append(text('p',ui("Observed hop categories are ordered numerically. Side-by-side columns show unique and repeated receptions; unidentified counts remain in the exact-count table. Unique/repeated classification spans the complete selected period, including copies observed with different hop counts. No missing hop categories are invented."),'muted'));exactCounts(host,rows,r=>`${r.hop_count} ${r.hop_count===1?'hop':'hops'}`);
    }
    function inspect(host){
        const message=text('p',ui("Hover, focus or tap a measurement for details."),'statistics-hover-value');message.setAttribute('role','status');message.setAttribute('aria-live','polite');host.append(message);
        return (node,value)=>{node.setAttribute('tabindex','0');node.setAttribute('aria-label',value);node.append(svg('title',{},value));for(const event of ['pointerenter','focus','click'])node.addEventListener(event,()=>{message.textContent=value;});};
    }
    function activeNeighbors(data){
        const host=$('statistics-active-neighbors');if(!host)return;host.replaceChildren();
        const rows=[...data.neighbors].sort((a,b)=>(b.incoming+b.outgoing)-(a.incoming+a.outgoing)||name(a).localeCompare(name(b))).slice(0,20);
        if(!rows.length){host.append(text('p',ui("No unambiguous adjacent flood-path relationships observed in this period."),'statistics-empty'));return;}
        const s=chart(host,ui("Most active observed neighbors"),rows.length*64+58),maximum=Math.max(1,...rows.map(r=>Math.max(r.incoming,r.outgoing))),interactive=inspect(host);
        rows.forEach((r,i)=>{const y=20+i*64,label=name(r),description=ui("{0} · We hear: {1} times; They hear: {2} times. Last observation: {3}. Observed route relationships, not confirmed RF reception.", label, r.incoming, r.outgoing, stamp(r.last_observed));
            const title=svg('text',{x:8,y:y+17},label.length>23?label.slice(0,22)+'…':label);interactive(title,description);s.append(title);
            for(const [field,color,offset]of [['incoming','#2563eb',0],['outgoing','#c75c0d',24]]){const value=r[field],width=value/maximum*480,bar=svg('rect',{x:205,y:y+offset,width,height:18,fill:color,class:'statistics-neighbor-bar','data-key':r.public_key,'data-direction':field,'data-value':value});interactive(bar,description);s.append(bar,svg('text',{x:695,y:y+offset+14},value));}
        });s.append(svg('text',{x:445,y:rows.length*64+42,'text-anchor':'middle'},ui("Observed receptions")));
        host.append(text('p',ui("Blue: We hear (incoming) · Orange: They hear (outgoing). Top ")+rows.length+ui(" neighbors by combined directional observations. Includes neighbors without coordinates. Ambiguous identities remain in the separate map list; this is not a ranking of RF link reliability."),'muted'));
        for(const note of data.notes||[])if(note.startsWith('Neighbor output'))host.append(text('p',ui(note)+ui(" Ranking uses this bounded summary."),'muted'));
    }
    const activityColors=['#eff6ff','#93c5fd','#3b82f6','#1d4ed8','#172554'];
    function activityColor(value,maximum){
        const scaled=Math.sqrt(Math.max(0,Math.min(1,value/maximum)))*(activityColors.length-1);
        const index=Math.min(activityColors.length-2,Math.floor(scaled)),fraction=scaled-index;
        const channel=(color,offset)=>parseInt(color.slice(offset,offset+2),16);
        const rgb=[1,3,5].map(offset=>Math.round(channel(activityColors[index],offset)*(1-fraction)+channel(activityColors[index+1],offset)*fraction));
        return `rgb(${rgb.join(',')})`;
    }
    function heatmap(data){
        const host=$('statistics-heatmap');if(!host)return;host.replaceChildren();const rows=data.activity_hourly||[];
        if(!rows.length){host.append(text('p',ui("No saved activity intervals available."),'statistics-empty'));return;}
        const zone=data.activity_timezone||window.meshcorestationDisplaySettings?.timezone||'Europe/Berlin',format=new Intl.DateTimeFormat('en-GB',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}),days=new Map();
        for(const row of rows){const parts=Object.fromEntries(format.formatToParts(new Date(row.at*1000)).map(p=>[p.type,p.value])),day=`${parts.year}-${parts.month}-${parts.day}`,hour=Number(parts.hour);
            if(!days.has(day))days.set(day,{at:row.at,hours:new Map()});const hours=days.get(day).hours;if(!hours.has(hour))hours.set(hour,[]);hours.get(hour).push(row);
        }
        const cell=28,left=110,top=34,width=left+24*cell+12,height=top+days.size*cell+36;
        const scroll=text('div','','statistics-heatmap-scroll');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',ui("Traffic activity by calendar day and hour; scroll horizontally"));
        const s=svg('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':ui("Observed flood-path activity by day and hour"),class:'statistics-heatmap-svg'});s.style.width=width+'px';scroll.append(s);host.append(scroll);const interactive=inspect(host),maximum=Math.max(1,...[...days.values()].flatMap(day=>[...day.hours.values()].map(intervals=>intervals.reduce((n,r)=>n+(r.receptions||0),0))));
        const defs=svg('defs'),pattern=svg('pattern',{id:'statistics-heatmap-gap',width:6,height:6,patternUnits:'userSpaceOnUse'});pattern.append(svg('path',{d:'M0 6L6 0',class:'statistics-gap-hatch'}));defs.append(pattern);s.append(defs);
        for(let h=0;h<24;h++)s.append(svg('text',{x:left+(h+.5)*cell,y:20,'text-anchor':'middle'},String(h).padStart(2,'0')));
        let i=0;for(const [day,entry]of days){const y=top+i++*cell;s.append(svg('text',{x:left-8,y:y+19,'text-anchor':'end'},window.meshcorestationFormatDate?.(entry.at,zone,{dateOnly:true})||day));
            for(let h=0;h<24;h++){
                const intervals=entry.hours.get(h)||[],positive=intervals.filter(r=>r.receptions!=null),count=positive.reduce((n,r)=>n+r.receptions,0),unknown=positive.length!==intervals.length||!intervals.length;
                const complete=intervals.length>0&&!unknown&&intervals.every(r=>r.complete),partial=positive.length>0&&!complete;
                const state=!intervals.length?ui("Outside selected window or skipped clock hour"):!positive.length?ui("Unknown recording gap"):complete?(count?ui("Recorded traffic"):ui("Recorded zero traffic")):ui("Incomplete observation coverage; counts are lower bounds");
                const rect=svg('rect',{x:left+h*cell,y,width:cell-2,height:cell-2,rx:3,fill:!positive.length?'url(#statistics-heatmap-gap)':count?activityColor(count,maximum):'var(--panel)',stroke:'var(--border)','stroke-dasharray':partial?'3 2':'','fill-opacity':1,class:'statistics-heatmap-cell'+(partial?' statistics-heatmap-incomplete':''),'data-day':day,'data-hour':h,'data-state':complete?'complete':partial?'incomplete':'unknown','data-count':positive.length?count:''});
                const details=`${window.meshcorestationFormatDate?.(entry.at,zone,{dateOnly:true})||day} · ${String(h).padStart(2,'0')}:00 · ${positive.length?count+ui(" observed receptions"):ui("Count unknown")}. ${state}. ${intervals.length>1?ui("Repeated clock hour; intervals are combined. "):''}`+intervals.map(r=>ui("{0} — {1}: {2} receptions, recording {3}/{4} seconds", stamp(Math.max(r.at,data.start)), stamp(Math.min(r.until||r.at+3600,data.end)), r.receptions??ui("unknown"), Math.round(r.coverage_seconds||0), Math.round(r.expected_seconds||0))).join('; ');
                interactive(rect,details);s.append(rect);
            }
        }
        s.append(svg('text',{x:left+12*cell,y:height-8,'text-anchor':'middle'},ui("Hour of day · ")+zone));
        const key=text('div','','statistics-heatmap-key');for(const [label,kind]of [[ui("Recorded zero"),'zero'],[ui("Observed traffic: lighter → darker (1–{0})", maximum),'traffic'],[ui("Incomplete coverage"),'incomplete'],[ui("Unknown / outside period"),'unknown']]){const item=text('span',label),sample=text('i','','statistics-heatmap-sample '+kind);if(kind==='traffic'){sample.style.background='linear-gradient(90deg,'+activityColors.join(',')+')';sample.classList.add('statistics-heatmap-ramp');}item.prepend(sample);key.append(item);}host.append(key);
        host.append(text('p',ui("All confidently attributed flood-path packet types; advertisement origins are excluded. A continuous, data-adaptive blue color scale preserves count precision; lighter cells indicate less traffic and darker cells more. Calendar-hour intervals use the dashboard time zone. Coverage uses elapsed time within the selected window; repeated daylight-saving hours are combined with their original intervals available above."),'muted'));
    }
    function packetTypes(data){
        const host=$('statistics-packet-types');if(!host)return;host.replaceChildren();const rows=data.packet_types||[],total=rows.reduce((n,r)=>n+r.receptions,0);
        if(!total){host.append(text('p',ui("No confidently attributed flood-path or full-key advertisement-origin observations in this period."),'statistics-empty'));return;}
        const typeNames=[ui("Request"),ui("Response"),ui("Direct text message"),ui("ACK / Acknowledgment"),ui("Advertisement"),ui("Group text message"),ui("Group data"),ui("Anonymous request"),ui("Path response"),ui("Trace"),ui("Multipart packet"),ui("Control / Discovery"),ui("Reserved code 12"),ui("Reserved code 13"),ui("Reserved code 14"),ui("Raw custom packet")];
        const colors=['#2563eb','#c75c0d','#168c6b','#a855f7','#be185d','#0891b2','#ca8a04','#4f46e5','#65a30d','#dc2626','#0f766e','#9333ea','#b45309','#64748b','#db2777','#0284c7'];
        const categories=[...new Set(rows.map(r=>String(r.packet_type??r.category)))].map(code=>[code,colors[Number(code)]||'#64748b',rows.filter(r=>String(r.packet_type??r.category)===code).reduce((n,r)=>n+r.receptions,0)]).sort((a,b)=>b[2]-a[2]||(Number(a[0])-Number(b[0]))||a[0].localeCompare(b[0],'en')),frame=text('div','','statistics-donut-layout'),s=svg('svg',{viewBox:'0 0 260 260',role:'img','aria-label':ui("Packet type distribution"),class:'statistics-donut'}),list=text('div','','statistics-donut-legend');frame.append(s,list);host.append(frame);const interactive=inspect(host);let offset=0;
        const circumference=2*Math.PI*82;
        for(const [category,color]of categories){const records=rows.filter(r=>String(r.packet_type??r.category)===category),count=records.reduce((n,r)=>n+r.receptions,0),percent=100*count/total;
            const detail=records.map(r=>`${r.evidence==='advertisement-origin'?ui("Advertisement origin (not forwarding)"):r.category==='Advertisements'?ui("Advertisement flood-path observations (route evidence)"):ui("Confirmed flood-path observations")}: ${countDescription(r)}`).join('; '),description=ui("{0}: {1} observations ({2}%). {3}", typeNames[Number(category)]||category, count, percent.toFixed(1), detail);
            if(count){const segment=svg('circle',{cx:130,cy:130,r:82,fill:'none',stroke:color,'stroke-width':34,'stroke-dasharray':`${circumference*count/total} ${circumference}`,'stroke-dashoffset':-offset,transform:'rotate(-90 130 130)',class:'statistics-donut-segment','data-category':category,'data-count':count});interactive(segment,description);s.append(segment);offset+=circumference*count/total;}
            const item=text('button','','statistics-packet-category');item.type='button';const swatch=text('i','','statistics-category-swatch');swatch.style.background=color;item.append(swatch,text('strong',typeNames[Number(category)]||ui("Unknown code ")+category),text('span',`${count} · ${percent.toFixed(1)}%`));if(Number(category)===4){const origins=records.filter(r=>r.evidence==='advertisement-origin').reduce((n,r)=>n+r.receptions,0);item.append(text('small',ui("Origin (not forwarding): {0} · Flood path: {1}", origins, count-origins),'statistics-evidence-split'));}item.title=description;item.addEventListener('click',()=>{host.querySelector('.statistics-hover-value').textContent=description;});list.append(item);
        }
        s.append(svg('text',{x:130,y:128,'text-anchor':'middle',class:'statistics-donut-total'},total),svg('text',{x:130,y:151,'text-anchor':'middle'},'observations'));
        host.append(text('p',ui("Receptions are counted, including repeated copies. Advertisement origins are full-key source observations, never forwarding events. Advertisements seen on flood paths are separately identified in the exact table. Ambiguous/unverified routes are excluded; Reserved and unknown codes retain their numeric identifiers. Percentages use only included observations and do not measure delivery success."),'muted'));
        const order=new Map(categories.map((r,i)=>[r[0],i]));
        exactCounts(host,[...rows].sort((a,b)=>order.get(String(a.packet_type??a.category))-order.get(String(b.packet_type??b.category))),r=>(typeNames[r.packet_type]||ui("Unknown code ")+r.category)+' · '+(r.evidence==='advertisement-origin'?ui("Advertisement origin (not forwarding)"):ui("Confirmed flood-path observation")),{percent:true});
    }
    function neighborSnr(data){
        const host=$('statistics-neighbor-snr');if(!host)return;host.replaceChildren();
        const rows=data.neighbor_snr||[];window.MeshcoreStationRepeaterNames?.ingest(rows);
        for(const [label,items]of [[ui("Identified neighbors"),rows.filter(r=>r.resolution==='matched')],[ui("Unknown or ambiguous prefixes"),rows.filter(r=>r.resolution!=='matched')]]){
            host.append(text('h4',label));if(!items.length){host.append(text('p',ui("No distinct valid measurements in this period."),'muted'));continue;}
            const scroll=text('div','','statistics-table-scroll'),table=document.createElement('table'),head=document.createElement('tr');
            for(const value of [ui("Repeater"),ui("Average SNR"),ui("Samples"),ui("Minimum"),ui("Maximum"),ui("Last Heard"),ui("Source")])head.append(text('th',value));table.append(head);
            for(const row of items){const tr=document.createElement('tr'),identity=document.createElement('td');
                identity.append(row.public_key?(window.MeshcoreStationRepeaterNames?.element(row.public_key)||text('span',row.name||row.public_key)):text('span',(row.resolution==='ambiguous'?ui("Ambiguous repeater"):ui("Unknown Repeater"))+' ('+row.prefix+'…)'));
                tr.append(identity,text('td',row.average_snr.toFixed(2)+' dB'+(row.samples===1?ui(" · single sample"):'')),text('td',row.samples),text('td',Number.isFinite(row.minimum_snr)?row.minimum_snr.toFixed(2)+' dB':ui("Not available")),text('td',Number.isFinite(row.maximum_snr)?row.maximum_snr.toFixed(2)+' dB':ui("Not available")),text('td',stamp(row.last_heard)),text('td',row.source==='firmware_aggregates'?ui("Firmware aggregates")+(row.sample_overflow?ui(" · incomplete samples"):''):ui("Legacy last-heard estimates")));table.append(tr);
            }scroll.append(table);host.append(scroll);
        }
        const quality=data.neighbor_snr_quality||{};
        if(quality.invalid_utc_records||quality.boundary_windows||quality.partial_collections||quality.sequence_gaps||quality.reported_loss)
            host.append(text('p',ui("Firmware data quality: {0} saved records without usable UTC (not assigned to this period); {1} with clock discontinuities; {2} boundary-crossing windows excluded; {3} partial collections and {4} sequence gaps noticed in this period. {5}", quality.invalid_utc_records||0, quality.discontinuous_records||0, quality.boundary_windows||0, quality.partial_collections||0, quality.sequence_gaps||0, quality.reported_loss?ui("Firmware reports cumulative retention/drop counters; some records may already be saved locally."):''),'stats-message'));
        host.append(text('p',ui("Firmware means use actual sample counts across whole UTC-valid windows. Legacy estimates are not blended into a neighbor’s firmware mean. Boundary-crossing windows are excluded. Legacy Last Heard is estimated from reported age and request timing. Overlapping equal-SNR estimates count once; source reception IDs are unavailable. Single samples provide insufficient history for a trend. Missing/invalid SNR or age values remain in raw poll history and are excluded here. These measurements do not confirm packet delivery."),'muted'));
    }
    function resizeVisible(){
        const host=$('statistics-neighbor-map');
        if(map&&host?.clientWidth&&host?.clientHeight){map.invalidateSize();if(mapNeedsFit&&mapPoints.length){map.fitBounds(mapPoints,{padding:[30,30],maxZoom:13});mapNeedsFit=false;}}
        if(lastData&&$('statistics-hourly')?.clientWidth){hourly(lastData);hopColumns(lastData);}
    }
    function regionName(name) {
        return name === 'Unknown' || name === 'Unscoped' ? ui(name) : name;
    }
    function regionalTraffic(data){
        const host=$('statistics-regions');if(!host)return;host.replaceChildren();
        const label=document.createElement('label'),check=document.createElement('input');
        check.type='checkbox';check.id='statistics-regions-all';check.checked=regionalAll;
        label.append(check,document.createTextNode(ui(" Show all messages (including duplicates)")));
        const plot=text('div','','statistics-regional-plot');host.append(label,plot);
        function draw(){
            const count=r=>regionalAll?r.receptions:r.unique_packets;
            const total=data.regions.reduce((n,r)=>n+count(r),0);
            const rows=data.regions.map(r=>({...r,percentage:total?100*count(r)/total:0})).sort((a,b)=>count(b)-count(a)||a.name.localeCompare(b.name,'en'));
            plot.replaceChildren();
            if(!rows.length){plot.append(text('p',ui("No confidently attributed observations in this period."),'statistics-empty'));return;}
            const s=chart(plot,ui("MeshCore regional traffic: upper unique messages and lower repeated receptions"),Math.max(160,rows.length*80+64));
            const maximum=Math.max(1,...rows.flatMap(r=>[r.unique_packets,r.repeated])),interactive=inspect(plot);
            s.classList.add('statistics-regional-chart');
            s.append(svg('text',{x:185,y:18},ui("Unique messages / repeated receptions")),svg('text',{x:890,y:18,'text-anchor':'end'},regionalAll?ui("All receptions / share"):ui("Unique total / share")));
            rows.forEach((r,i)=>{
                const y=34+i*80;
                const description=ui("{0}: {1} unique messages; {2} repeated receptions; {3} total observed receptions; {4} unidentified. Ranking uses {5} {6} ({7}%). Packet digests are deduplicated within each region.", regionName(r.name), r.unique_packets, r.repeated, r.receptions, r.unidentified, count(r), regionalAll?ui("all receptions"):ui("unique messages"), r.percentage.toFixed(1));
                const label=regionName(r.name);
                const category=svg('text',{x:8,y:y+15},label.length>22?label.slice(0,20)+'…':label);interactive(category,description);s.append(category);
                for(const [field,color,offset,label]of [['unique_packets','#2563eb',0,'unique'],['repeated','#c75c0d',26,'repeated']]){
                    const value=r[field],bar=svg('rect',{x:185,y:y+offset,width:value/maximum*400,height:18,fill:color,class:'statistics-region-bar','data-name':r.name,'data-series':field,'data-value':value,'data-count':count(r),'data-total':r.receptions,'data-percentage':r.percentage,'data-mode':regionalAll?'all':'unique'});
                    interactive(bar,description);s.append(bar);
                    const number=svg('text',{x:600,y:y+offset+14,class:'statistics-region-series-count'},`${value} ${ui(label)}`);interactive(number,description);s.append(number);
                }
                const total=svg('text',{x:890,y:y+27,'text-anchor':'end',class:'statistics-region-value'},`${count(r)} · ${r.percentage.toFixed(1)}%`);interactive(total,description);s.append(total);
            });
            plot.append(text('p',ui("Blue upper bar: Unique messages · Orange lower bar: Repeated receptions. Both bars use the same numerical scale in either ranking mode."),'statistics-chart-legend'));
            plot.append(text('p',regionalAll?ui("Regions are ranked by all confirmed regional receptions, including duplicate and forwarded copies. Totals and percentages include those receptions."):ui("Regions are ranked by unique packet digests within each region. Totals and percentages exclude duplicates; repeated receptions remain visible for context."),'muted'));
            plot.append(text('p',ui("Bar counts do not change when the ranking mode changes. Unidentified payloads are included in all-reception totals but remain separate from unique/repeated bars in the exact-count table. Ambiguous and unverified observations remain excluded. The exact-count table retains all saved counts; its shares follow the active ranking mode."),'muted'));
            exactCounts(plot,rows,r=>regionName(r.name),{percent:true});
        }
        check.addEventListener('change',()=>{regionalAll=check.checked;draw();});draw();
    }
    document.addEventListener('change',event=>{if(event.target.id==='statistics-show-one-way')$('statistics-neighbor-map')?.classList.toggle('hide-one-way',!event.target.checked);});
    document.addEventListener('repeater-names-updated',()=>{if(!lastData)return;activeNeighbors(lastData);neighborSnr(lastData);if(map)for(const item of Object.values(map._layers)){if(item.options?.identityKey)item.getElement()?.setAttribute('title',name({public_key:item.options.identityKey}));}});
    function disposeMap(){generation++;resize?.disconnect();resize=null;map?.remove();map=null;}
    function dispose(){disposeMap();chartResize?.disconnect();chartResize=null;}
    function observeCharts(data){
        chartResize?.disconnect();chartResize=null;
        const host=$('statistics-hourly');if(!host||!window.ResizeObserver)return;
        let width=host.clientWidth;
        const observer=new ResizeObserver(()=>{if(chartResize!==observer)return;const next=host.clientWidth;if(next>0&&Math.abs(next-width)>1){width=next;hourly(data);hopColumns(data);}});
        chartResize=observer;observer.observe(host);
    }
    function position(r){return r&&typeof r.latitude==='number'&&typeof r.longitude==='number'&&Number.isFinite(r.latitude)&&Number.isFinite(r.longitude)&&Math.abs(r.latitude)<=90&&Math.abs(r.longitude)<=180&&(r.latitude!==0||r.longitude!==0)?[r.latitude,r.longitude]:null;}
    function neighborSummary(r){
        const box=text('div','','statistics-neighbor-summary'),heading=text('strong',name(r),'statistics-neighbor-name');heading.title=name(r);box.append(heading);
        for(const[label,value]of[[ui("We hear: "),r.incoming],[ui("They hear: "),r.outgoing]]){const row=text('div','','statistics-neighbor-count');row.append(text('span',label),text('span',ui("{0} times", value)));box.append(row);}return box;
    }
    function popup(selected,r){const box=document.createElement('div');box.append(neighborSummary(r),text('strong',`${name(selected)} ${r.incoming&&r.outgoing?'↔':r.outgoing?'→':'←'} ${name(r)}`),text('p',ui("{0} → {1}: {2} receptions; {3} unique packets", name(selected), name(r), r.outgoing, r.outgoing_unique||0)),text('p',ui("{0} → {1}: {2} receptions; {3} unique packets", name(r), name(selected), r.incoming, r.incoming_unique||0)),text('p',ui("Last observation: {0}", stamp(r.last_observed))),text('p',ui("A direction with no observations is not proof that communication is impossible.")),text('p',ui("Relationships are inferred from observed flood routes, not verified direct RF links.")),text('p',ui("Public keys: {0} / {1}", selected.public_key, r.public_key),'map-key'));return box;}
    async function neighborMap(data){
        const host=$('statistics-neighbor-map'),note=$('statistics-map-notes'),missing=$('statistics-missing-coordinates'),uncertain=$('statistics-ambiguous');if(!host)return;
        disposeMap();const ticket=generation;host.replaceChildren();note.replaceChildren();missing.replaceChildren();uncertain.replaceChildren();
        const selected=data.selected_repeater;
        window.MeshcoreStationRepeaterNames?.ingest([selected,...data.neighbors].filter(Boolean));
        for(const r of data.neighbors)if(!position(r))missing.append(text('li',ui("{0} — {1} incoming / {2} outgoing observations; coordinates unavailable.", name(r), r.incoming, r.outgoing)));
        for(const r of data.ambiguous)uncertain.append(text('li',ui("{0} · {1} · {2} receptions · last {3} · ambiguous/unresolved hash evidence; {4} current neighbor candidates.", r.direction==='incoming'?r.identity.split(' → ').reverse().join(' → '):r.identity, r.direction, r.receptions, stamp(r.last_observed), r.candidate_count??r.candidates.length)));
        if(!data.ambiguous.length)uncertain.append(text('li',ui("No ambiguous adjacent-path relationships recorded in this period.")));
        if(!selected){note.append(text('p',ui("Select a managed repeater to view saved path relationships.")));return;}
        if(!position(selected))note.append(text('p',ui("Selected repeater coordinates are unavailable. Relationship lines cannot be positioned.")));
        const summary=text('p',ui("{0} observed neighbors · {1} two-way · {2} one-way. Green: two-way observed. Red: one-way observed. Blue marker: selected repeater. Arrows show observed directions.", data.neighbors.length, data.neighbors.filter(r=>r.incoming&&r.outgoing).length, data.neighbors.filter(r=>!r.incoming||!r.outgoing).length),'statistics-map-legend');note.append(summary);for(const message of data.notes||[])note.append(text('p',ui(message),'muted'));
        try{
            await window.meshcorestationLoadMapLibrary();if(ticket!==generation)return;
            map=L.map(host,{maxZoom:19});mapNeedsFit=!host.clientWidth||!host.clientHeight;const layer=L.layerGroup().addTo(map),points=[];
            function marker(r,selectedMarker=false){const p=position(r);if(!p)return;points.push(p);const dot=text('span',selectedMarker?'S':'R',selectedMarker?'statistics-marker selected':'statistics-marker');const marker=L.marker(p,{title:name(r),identityKey:r.public_key,icon:L.divIcon({html:dot,className:'statistics-map-icon'+(!selectedMarker&&(!r.incoming||!r.outgoing)?' statistics-one-way':''),iconSize:[28,28],iconAnchor:[14,14]})}).addTo(layer);
                if(!selectedMarker)marker.bindTooltip(()=>neighborSummary(r),{direction:'top',offset:[0,-16],opacity:1,className:'statistics-neighbor-tooltip'});
                marker.bindPopup(()=>selectedMarker?text('strong',name(r)):popup(selected,r));
                // Tap/click retains the detailed popup with the same summary,
                // and closes the hover balloon so the two do not overlap.
                if(!selectedMarker)marker.on('click',()=>marker.closeTooltip());}
            marker(selected,true);for(const r of data.neighbors)marker(r);
            for(const r of data.neighbors){const a=position(selected),b=position(r);if(!a||!b)continue;const color=r.incoming&&r.outgoing?'#15803d':'#dc2626';L.polyline([a,b],{color,weight:4,opacity:.95,className:(!r.incoming||!r.outgoing)?'statistics-one-way':''}).addTo(layer).bindPopup(()=>popup(selected,r));
                const pa=map.project(a,8),pb=map.project(b,8);
                for(const outgoing of [true,false])if(outgoing?r.outgoing:r.incoming){const angle=Math.atan2(pb.y-pa.y,pb.x-pa.x)+(outgoing?0:Math.PI),ratio=outgoing?.6:.4;
                    const mid=map.unproject(L.point(pa.x+(pb.x-pa.x)*ratio,pa.y+(pb.y-pa.y)*ratio),8),arrow=text('span','','route-direction-arrow');arrow.style.borderLeftColor=color;arrow.style.transform=`rotate(${angle}rad)`;
                    L.marker(mid,{interactive:false,icon:L.divIcon({html:arrow,className:'route-arrow-icon'+((!r.incoming||!r.outgoing)?' statistics-one-way':''),iconSize:[20,20],iconAnchor:[10,10]})}).addTo(layer);
                }
            }
            mapPoints=points;
            if(points.length&&!mapNeedsFit)map.fitBounds(points,{padding:[30,30],maxZoom:13});else map.setView(points[0]||[51,10],points.length?10:5);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:ui("© OpenStreetMap contributors")}).on('tileerror',()=>{if(ticket===generation&&!note.querySelector('.tile-warning'))note.append(text('p',ui("Background tiles unavailable; observed markers and lines remain visible."),'tile-warning'));}).addTo(map);
            if(window.ResizeObserver){resize=new ResizeObserver(resizeVisible);resize.observe(host);}
            requestAnimationFrame(()=>{if(ticket===generation)map?.invalidateSize();});
        }catch(error){if(ticket===generation)note.append(text('p',ui("Map unavailable: ")+error.message+ui(". Saved charts and relationship lists remain available."),'statistics-error'));}
    }
    window.MeshcoreStationStatisticsVisuals={dispose,resize:resizeVisible,stale(){
        dispose();for(const id of ['statistics-neighbor-snr','statistics-active-neighbors','statistics-heatmap','statistics-packet-types','statistics-hourly','statistics-hops','statistics-regions','statistics-neighbor-map','statistics-map-notes','statistics-missing-coordinates','statistics-ambiguous'])$(id)?.classList.add('statistics-stale');
        if($('statistics-coverage-summary')?.textContent&&!$('statistics-coverage-summary').textContent.startsWith('Previous snapshot'))$('statistics-coverage-summary').textContent=ui("Previous snapshot · ")+$('statistics-coverage-summary').textContent;
        if($('statistics-coverage')?.textContent&&!$('statistics-coverage').textContent.startsWith('Previous snapshot'))$('statistics-coverage').textContent=ui("Previous snapshot — ")+$('statistics-coverage').textContent;
    },render(data){
        window.MeshcoreStationRepeaterNames?.ingest([data.selected_repeater,...data.neighbors,...(data.neighbor_snr||[])].filter(Boolean));
        lastData=data;
        for(const id of ['statistics-neighbor-snr','statistics-active-neighbors','statistics-heatmap','statistics-packet-types','statistics-hourly','statistics-hops','statistics-regions','statistics-neighbor-map','statistics-map-notes','statistics-missing-coordinates','statistics-ambiguous'])$(id)?.classList.remove('statistics-stale');
        if($('statistics-coverage-summary'))$('statistics-coverage-summary').textContent=ui("Recorded collection coverage: ")+(data.coverage_known?(100*data.coverage_seconds/data.coverage_expected).toFixed(1)+'%':ui("Unknown"));
        if($('statistics-coverage'))$('statistics-coverage').textContent=ui("{0} — {1}. Recorded collection coverage: {2} {3} ambiguous, unverified or non-forwarding receptions excluded from confirmed totals. Historical hours without uptime records have unknown coverage.", stamp(data.start), stamp(data.end), data.coverage_known?(100*data.coverage_seconds/data.coverage_expected).toFixed(1)+ui("% with recorded uptime; the remainder is unknown."):ui("Unknown (no saved uptime evidence for this history)."), data.excluded);
        neighborSnr(data);hourly(data);hopColumns(data);activeNeighbors(data);heatmap(data);packetTypes(data);regionalTraffic(data);neighborMap(data);observeCharts(data);
    }};
})();
