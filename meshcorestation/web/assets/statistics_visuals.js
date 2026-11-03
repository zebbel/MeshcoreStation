/* Saved passive observations only; native chart SVGs never style Leaflet SVGs. */
(() => {
    const $=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg';
    let map=null,resize=null,chartResize=null,generation=0;
    const text=(tag,value,cls)=>{const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;};
    const stamp=value=>window.meshcorestationFormatDate?.(value)||new Date(value*1000).toLocaleString('en-GB');
    const name=r=>window.MeshcoreStationRepeaterNames?.label(r.public_key)||r.name||`Unknown Repeater (${r.public_key.slice(0,8)}…)`;
    function svg(tag,attributes={},content){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attributes))e.setAttribute(k,v);if(content!==undefined)e.textContent=content;return e;}
    function chart(host,label,height=260){const s=svg('svg',{viewBox:`0 0 900 ${height}`,role:'img','aria-label':label});host.replaceChildren(s);return s;}
    function legend(host,unidentified=true){host.append(text('p','Unique packets · blue | Repeated receptions · orange'+(unidentified?' | Unidentified payloads · gray':''),'statistics-chart-legend'));}
    function exactCounts(host,rows,labelOf,{percent=false,coverage=false}={}){
        const details=document.createElement('details');details.append(text('summary',coverage?'Show exact hourly counts':'Show exact counts'));
        let populated=false;
        details.addEventListener('toggle',()=>{
            if(!details.open||populated)return;populated=true;
            const scroll=text('div','','statistics-table-scroll'),table=document.createElement('table'),head=document.createElement('tr');
            for(const v of ['Category','Receptions','Unique','Repeated','Unidentified',...(coverage?['Coverage']:[]),...(percent?['Share']:[])])head.append(text('th',v));table.append(head);
            for(const r of rows){const row=document.createElement('tr');for(const v of [labelOf(r),r.receptions??'Unknown',r.unique_packets??'Unknown',r.repeated??'Unknown',r.unidentified??'Unknown',...(coverage?[r.complete?'Complete':'Incomplete / unknown']:[]),...(percent?[r.percentage.toFixed(1)+'%']:[])])row.append(text('td',v));table.append(row);}
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
        scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',label+'; scroll horizontally to inspect every interval');scroll.dataset.view=key;
        const s=svg('svg',{viewBox:`0 0 ${width} ${height}`,class:'statistics-column-chart',role:'img','aria-label':label});s.style.width=width+'px';
        for(let value=0;value<=top;value+=step){axis.append(svg('text',{x:59,y:y(value)+4,'text-anchor':'end'},value));s.append(svg('line',{x1:0,y1:y(value),x2:width,y2:y(value),class:'statistics-grid'}));}
        axis.append(svg('text',{transform:'translate(8 135) rotate(-90)','text-anchor':'middle',class:'statistics-axis-title'},'Observed receptions'));
        scroll.append(s);frame.append(axis,scroll);host.append(frame);
        const hover=text('p','Hover, focus or tap a column to inspect counts.','statistics-hover-value');hover.setAttribute('role','status');hover.setAttribute('aria-live','polite');host.append(hover);
        const spacing=width/Math.max(1,rows.length);
        function interactive(node,value){node.setAttribute('tabindex','0');node.setAttribute('aria-label',value);node.append(svg('title',{},value));for(const event of ['pointerenter','focus','click'])node.addEventListener(event,()=>{hover.textContent=value;});}
        if(width>viewport+1){const controls=text('div','','statistics-chart-navigation');controls.append(text('span','Scroll horizontally to inspect every interval.','muted'));
            for(const[title,left]of [['Start',0],[latest?'Latest hours':'Highest hop counts',width]]){const button=text('button',title,'secondary');button.type='button';button.addEventListener('click',()=>{scroll.scrollLeft=left;});controls.append(button);}host.append(controls);
        }
        requestAnimationFrame(()=>{if(scroll.isConnected)scroll.scrollLeft=saved??(latest?width:0);});
        return {s,y,base,plot,width,spacing,interactive};
    }
    function countDescription(r){return `${r.receptions??'Unknown'} receptions; ${r.unique_packets??'Unknown'} unique; ${r.repeated??'Unknown'} repeated; ${r.unidentified??'Unknown'} unidentified`;}
    function hourly(data){
        const host=$('statistics-hourly');if(!host)return;const rows=data.hourly;
        const max=Math.max(1,...rows.map(r=>Math.max(r.unique_packets||0,r.repeated||0)));
        const f=columns(host,'Observed text messages per hour',rows,max,{key:data.selected+'|'+data.days,minimum:24,latest:true});
        const gapId='statistics-hourly-gap',defs=svg('defs'),pattern=svg('pattern',{id:gapId,width:8,height:8,patternUnits:'userSpaceOnUse'});pattern.append(svg('path',{d:'M-2 2L2-2M0 8L8 0M6 10L10 6',class:'statistics-gap-hatch'}));defs.append(pattern);f.s.prepend(defs);
        rows.forEach((r,i)=>{
            const left=i*f.spacing,unknown=r.unique_packets==null||r.repeated==null,coverage=r.complete?'Complete recording coverage':'Incomplete / unknown coverage; observed counts are lower bounds';
            const group=svg('g',{class:'statistics-hour','data-at':r.at});
            if(unknown){const gap=svg('rect',{x:left,y:f.base-f.plot,width:f.spacing,height:f.plot,fill:`url(#${gapId})`,class:'statistics-coverage-gap'});f.interactive(gap,`${stamp(r.at)} · Unknown traffic; collection coverage is not verified. This is not a zero.`);group.append(gap);}
            else{
                const barWidth=Math.min(20,Math.max(3,(f.spacing-6)/2)),center=left+f.spacing/2;
                for(const[field,color,offset]of[['unique_packets','#2563eb',-barWidth-1],['repeated','#c75c0d',1]]){
                    const value=r[field],bar=svg('rect',{x:center+offset,y:f.y(value),width:barWidth,height:f.base-f.y(value),fill:color,stroke:color,'stroke-width':r.complete?0:1.5,'stroke-dasharray':r.complete?'':'3 2',class:'statistics-hour-bar'+(r.complete?'':' statistics-incomplete'),'data-series':field,'data-value':value});
                    f.interactive(bar,`${stamp(r.at)} · ${field==='unique_packets'?'Unique packets':'Repeated receptions'}: ${value}. ${countDescription(r)}. ${coverage}.`);group.append(bar);
                }
                if(r.receptions===0&&r.complete){const zero=svg('text',{x:center,y:f.base-5,'text-anchor':'middle',class:'statistics-confirmed-zero'},'0');f.interactive(zero,`${stamp(r.at)} · 0 text receptions during a fully recorded interval.`);group.append(zero);}
                if(r.receptions>0&&!r.unique_packets&&!r.repeated){const other=svg('text',{x:center,y:f.base-5,'text-anchor':'middle',class:'statistics-unplotted'},'?');f.interactive(other,`${stamp(r.at)} · ${r.unidentified} unidentified receptions retained in the exact-count table, not plotted as unique or repeated.`);group.append(other);}
            }
            f.s.append(group);
            const interval=Math.max(1,Math.ceil(145/f.spacing));
            if(i%interval===0||i===rows.length-1){const last=i===rows.length-1;if(last&&i%interval<interval/2&&i!==0)return;const tick=svg('text',{x:left+f.spacing/2,y:244,'text-anchor':i===0?'start':last?'end':'middle',class:'statistics-time-tick'}),parts=stamp(r.at).split(' ');tick.append(svg('tspan',{x:left+f.spacing/2},parts.shift()),svg('tspan',{x:left+f.spacing/2,dy:17},parts.join(' ')));f.s.append(tick);}
        });
        f.s.append(svg('text',{x:f.width/2,y:289,'text-anchor':'middle',class:'statistics-axis-title'},'Hour · '+(window.meshcorestationDisplaySettings?.timezone||'dashboard time zone')));
        legend(host,false);host.append(text('p','Group and direct-text payloads on confidently attributed flood paths. Dashed bars are incomplete lower bounds; hatched gaps are unknown, not zero traffic. Unidentified receptions remain in the table. Unique/repeated counts are calculated within each hour.','muted'));
        if(!rows.some(r=>r.receptions!=null))host.append(text('p','No confirmed text observations or verified collection coverage in this period.','statistics-empty'));
        exactCounts(host,rows,r=>stamp(r.at),{coverage:true});
    }
    function hopColumns(data){
        const host=$('statistics-hops');if(!host)return;const rows=[...data.hops].sort((a,b)=>a.hop_count-b.hop_count);
        if(!rows.length){host.replaceChildren(text('p','No confidently attributed observations in this period.','statistics-empty'));return;}
        const total=r=>r.unique_packets+r.repeated,max=Math.max(1,...rows.map(total));
        const f=columns(host,'Observed total route hop count',rows,max,{key:data.selected+'|'+data.days,minimum:56});
        rows.forEach((r,i)=>{const center=(i+.5)*f.spacing,width=Math.min(64,f.spacing*.65),description=`${r.hop_count} ${r.hop_count===1?'hop':'hops'}: ${countDescription(r)}. Columns show identified receptions; unidentified counts remain in the table.`;let accumulated=0;
            for(const[field,color]of[['unique_packets','#2563eb'],['repeated','#c75c0d']]){const value=r[field],bottom=f.y(accumulated);accumulated+=value;const bar=svg('rect',{x:center-width/2,y:f.y(accumulated),width,height:bottom-f.y(accumulated),fill:color,class:'statistics-hop-bar','data-hop':r.hop_count,'data-series':field,'data-value':value});f.interactive(bar,description);f.s.append(bar);}
            const label=svg('text',{x:center,y:f.y(total(r))-7,'text-anchor':'middle',class:'statistics-column-total'},total(r)||'?');f.interactive(label,description);f.s.append(label,svg('text',{x:center,y:246,'text-anchor':'middle',class:'statistics-hop-tick','data-hop':r.hop_count},r.hop_count));
        });f.s.append(svg('text',{x:f.width/2,y:282,'text-anchor':'middle',class:'statistics-axis-title'},'Total route hop count'));
        legend(host,false);host.append(text('p','Observed hop categories are ordered numerically. Columns stack unique and repeated receptions; unidentified counts remain in the exact-count table. No missing hop categories are invented.','muted'));exactCounts(host,rows,r=>`${r.hop_count} ${r.hop_count===1?'hop':'hops'}`);
    }
    function ranking(id,rows,labelOf,title,percent=false){
        const host=$(id);if(!host)return;
        host.replaceChildren();if(!rows.length){host.append(text('p','No confidently attributed observations in this period.','statistics-empty'));return;}
        const height=Math.max(140,rows.length*48+40),s=chart(host,title,height),max=Math.max(1,...rows.map(r=>r.receptions));
        rows.forEach((r,i)=>{
            const y=20+i*48,label=labelOf(r),values=[r.unique_packets,r.repeated,r.unidentified];let x=185;
            const category=svg('text',{x:8,y:y+15},label.length>22?label.slice(0,20)+'…':label);category.append(svg('title',{},label));s.append(category);
            values.forEach((value,j)=>{const width=value/max*480;const bar=svg('rect',{x,y,width,height:22,fill:['#2563eb','#c75c0d','#64748b'][j],tabindex:'0'});bar.append(svg('title',{},`${label}: ${r.receptions} receptions; ${r.unique_packets} unique; ${r.repeated} repeated; ${r.unidentified} unidentified${percent?`; ${r.percentage.toFixed(1)}% of confirmed receptions`:''}`));s.append(bar);x+=width;});
            s.append(svg('text',{x:680,y:y+16},`${r.receptions}${percent?' · '+r.percentage.toFixed(1)+'%':''}`));
        });legend(host);
        exactCounts(host,rows,labelOf,{percent});
    }
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
    function neighborSummary(r){const box=text('div','','statistics-neighbor-summary');box.append(text('strong',name(r)),text('p',`We hear: ${r.incoming} times`),text('p',`They hear: ${r.outgoing} times`));return box;}
    function popup(selected,r){const box=document.createElement('div');box.append(neighborSummary(r),text('strong',`${name(selected)} ${r.incoming&&r.outgoing?'↔':r.outgoing?'→':'←'} ${name(r)}`),text('p',`${name(selected)} → ${name(r)}: ${r.outgoing} receptions; ${r.outgoing_unique||0} unique packets`),text('p',`${name(r)} → ${name(selected)}: ${r.incoming} receptions; ${r.incoming_unique||0} unique packets`),text('p',`Last observation: ${stamp(r.last_observed)}`),text('p','A direction with no observations is not proof that communication is impossible.'),text('p','Relationships are inferred from observed flood routes, not verified direct RF links.'),text('p',`Public keys: ${selected.public_key} / ${r.public_key}`,'map-key'));return box;}
    async function neighborMap(data){
        const host=$('statistics-neighbor-map'),note=$('statistics-map-notes'),missing=$('statistics-missing-coordinates'),uncertain=$('statistics-ambiguous');if(!host)return;
        disposeMap();const ticket=generation;host.replaceChildren();note.replaceChildren();missing.replaceChildren();uncertain.replaceChildren();
        const selected=data.selected_repeater;
        window.MeshcoreStationRepeaterNames?.ingest([selected,...data.neighbors].filter(Boolean));
        for(const r of data.neighbors)if(!position(r))missing.append(text('li',`${name(r)} — ${r.incoming} incoming / ${r.outgoing} outgoing observations; coordinates unavailable.`));
        for(const r of data.ambiguous)uncertain.append(text('li',`${r.direction==='incoming'?r.identity.split(' → ').reverse().join(' → '):r.identity} · ${r.direction} · ${r.receptions} receptions · last ${stamp(r.last_observed)} · ambiguous/unresolved hash evidence; ${r.candidate_count??r.candidates.length} current neighbor candidates.`));
        if(!data.ambiguous.length)uncertain.append(text('li','No ambiguous adjacent-path relationships recorded in this period.'));
        if(!selected){note.append(text('p','Select a managed repeater to view saved path relationships.'));return;}
        if(!position(selected))note.append(text('p','Selected repeater coordinates are unavailable. Relationship lines cannot be positioned.'));
        const summary=text('p',`${data.neighbors.length} observed neighbors · ${data.neighbors.filter(r=>r.incoming&&r.outgoing).length} two-way · ${data.neighbors.filter(r=>!r.incoming||!r.outgoing).length} one-way. Green: two-way observed. Red: one-way observed. Blue marker: selected repeater. Arrows show observed directions.`,'statistics-map-legend');note.append(summary);for(const message of data.notes||[])note.append(text('p',message,'muted'));
        try{
            await window.meshcorestationLoadMapLibrary();if(ticket!==generation)return;
            map=L.map(host,{maxZoom:19});const layer=L.layerGroup().addTo(map),points=[];
            function marker(r,selectedMarker=false){const p=position(r);if(!p)return;points.push(p);const dot=text('span',selectedMarker?'S':'R',selectedMarker?'statistics-marker selected':'statistics-marker');const marker=L.marker(p,{title:name(r),icon:L.divIcon({html:dot,className:'statistics-map-icon',iconSize:[28,28],iconAnchor:[14,14]})}).addTo(layer);
                if(!selectedMarker)marker.bindTooltip(neighborSummary(r),{direction:'top',offset:[0,-16],opacity:1,className:'statistics-neighbor-tooltip'});
                marker.bindPopup(selectedMarker?text('strong',name(r)):popup(selected,r));
                // Tap/click retains the detailed popup with the same summary,
                // and closes the hover balloon so the two do not overlap.
                if(!selectedMarker)marker.on('click',()=>marker.closeTooltip());}
            marker(selected,true);for(const r of data.neighbors)marker(r);
            for(const r of data.neighbors){const a=position(selected),b=position(r);if(!a||!b)continue;const color=r.incoming&&r.outgoing?'#15803d':'#dc2626';L.polyline([a,b],{color,weight:4,opacity:.95}).addTo(layer).bindPopup(popup(selected,r));
                const pa=map.project(a,8),pb=map.project(b,8);
                for(const outgoing of [true,false])if(outgoing?r.outgoing:r.incoming){const angle=Math.atan2(pb.y-pa.y,pb.x-pa.x)+(outgoing?0:Math.PI),ratio=outgoing?.6:.4;
                    const mid=map.unproject(L.point(pa.x+(pb.x-pa.x)*ratio,pa.y+(pb.y-pa.y)*ratio),8),arrow=text('span','','route-direction-arrow');arrow.style.borderLeftColor=color;arrow.style.transform=`rotate(${angle}rad)`;
                    L.marker(mid,{interactive:false,icon:L.divIcon({html:arrow,className:'route-arrow-icon',iconSize:[20,20],iconAnchor:[10,10]})}).addTo(layer);
                }
            }
            if(points.length)map.fitBounds(points,{padding:[30,30],maxZoom:13});else map.setView([51,10],5);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).on('tileerror',()=>{if(ticket===generation&&!note.querySelector('.tile-warning'))note.append(text('p','Background tiles unavailable; observed markers and lines remain visible.','tile-warning'));}).addTo(map);
            if(window.ResizeObserver){resize=new ResizeObserver(()=>map?.invalidateSize());resize.observe(host);}
            requestAnimationFrame(()=>{if(ticket===generation)map?.invalidateSize();});
        }catch(error){if(ticket===generation)note.append(text('p','Map unavailable: '+error.message+'. Saved charts and relationship lists remain available.','statistics-error'));}
    }
    window.MeshcoreStationStatisticsVisuals={dispose,stale(){
        dispose();for(const id of ['statistics-hourly','statistics-hops','statistics-regions','statistics-neighbor-map','statistics-map-notes','statistics-missing-coordinates','statistics-ambiguous'])$(id)?.classList.add('statistics-stale');
        if($('statistics-coverage')?.textContent&&!$('statistics-coverage').textContent.startsWith('Previous snapshot'))$('statistics-coverage').textContent='Previous snapshot — '+$('statistics-coverage').textContent;
    },render(data){
        for(const id of ['statistics-hourly','statistics-hops','statistics-regions','statistics-neighbor-map','statistics-map-notes','statistics-missing-coordinates','statistics-ambiguous'])$(id)?.classList.remove('statistics-stale');
        if($('statistics-coverage'))$('statistics-coverage').textContent=`${stamp(data.start)} — ${stamp(data.end)}. Recorded collection coverage: ${data.coverage_known?(100*data.coverage_seconds/data.coverage_expected).toFixed(1)+'% with recorded uptime; the remainder is unknown.':'Unknown (no saved uptime evidence for this history).'} ${data.excluded} ambiguous, unverified or non-forwarding receptions excluded from confirmed totals. Historical hours without uptime records have unknown coverage.`;
        hourly(data);hopColumns(data);ranking('statistics-regions',data.regions,r=>r.name,'MeshCore regional traffic',true);neighborMap(data);observeCharts(data);
    }};
})();
