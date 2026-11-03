/* Saved passive observations only; native chart SVGs never style Leaflet SVGs. */
(() => {
    const $=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg';
    let map=null,resize=null,generation=0;
    const text=(tag,value,cls)=>{const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;};
    const stamp=value=>window.meshcorestationFormatDate?.(value)||new Date(value*1000).toLocaleString('en-GB');
    const name=r=>window.MeshcoreStationRepeaterNames?.label(r.public_key)||r.name||`Unknown Repeater (${r.public_key.slice(0,8)}…)`;
    function svg(tag,attributes={},content){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attributes))e.setAttribute(k,v);if(content!==undefined)e.textContent=content;return e;}
    function chart(host,label,height=260){const s=svg('svg',{viewBox:`0 0 900 ${height}`,role:'img','aria-label':label});host.replaceChildren(s);return s;}
    function legend(host){const e=text('p','Unique packets · blue | Repeated receptions · orange | Unidentified payloads · gray','statistics-chart-legend');host.append(e);}
    function hourly(data){
        const host=$('statistics-hourly');if(!host)return;
        const s=chart(host,'Observed text messages per hour');const rows=data.hourly;
        const max=Math.max(1,...rows.map(r=>(r.receptions||0)));const top=Math.max(1,Math.ceil(max));
        const x=i=>55+i*810/Math.max(1,rows.length-1),y=v=>210-v/top*175;
        for(const value of [...new Set([0,Math.ceil(top/2),top])]){s.append(svg('line',{x1:55,y1:y(value),x2:865,y2:y(value),class:'statistics-grid'}),svg('text',{x:45,y:y(value)+4,'text-anchor':'end'},value));}
        for(const[field,color]of[['unique_packets','#2563eb'],['repeated','#c75c0d'],['unidentified','#64748b']]){
            let d='',continuing=false;
            rows.forEach((r,i)=>{
                const value=r[field];if(value==null){continuing=false;return;}
                if(r.complete){d+=(continuing?' L':' M')+x(i)+' '+y(value);continuing=true;}else continuing=false;
                const point=svg('circle',{cx:x(i),cy:y(value),r:rows.length>180?2:3,stroke:color,fill:r.complete?color:'var(--panel)',tabindex:'0'});
                point.append(svg('title',{},`${stamp(r.at)} · ${field==='unique_packets'?'Unique packets':field==='repeated'?'Repeated receptions':'Unidentified payloads'}: ${value}; ${r.complete?'recorded interval':'incomplete/unknown collection coverage'}`));s.append(point);
            });
            s.append(svg('path',{d,stroke:color,fill:'none','stroke-width':2}));
        }
        for(const i of [...new Set([0,Math.floor((rows.length-1)/2),rows.length-1])])if(rows[i])s.append(svg('text',{x:x(i),y:240,'text-anchor':i===0?'start':i===rows.length-1?'end':'middle'},stamp(rows[i].at)));
        legend(host);host.append(text('p','Group text and direct-text payloads on confidently attributed flood routes. Empty unverified hours are gaps; hollow points show incomplete coverage. Counts in incomplete hours are lower bounds. Unique/repeated counts are calculated within each hour.','muted'));
        if(!rows.some(r=>r.receptions!=null))host.append(text('p','No confirmed text observations or verified collection coverage in this period.','statistics-empty'));
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
        const details=document.createElement('details');details.append(text('summary','Show exact counts'));
        const table=document.createElement('table');const head=document.createElement('tr');for(const v of ['Category','Receptions','Unique','Repeated','Unidentified',...(percent?['Share']:[])])head.append(text('th',v));table.append(head);
        for(const r of rows){const row=document.createElement('tr');for(const v of [labelOf(r),r.receptions,r.unique_packets,r.repeated,r.unidentified,...(percent?[r.percentage.toFixed(1)+'%']:[])])row.append(text('td',v));table.append(row);}details.append(table);host.append(details);
    }
    function dispose(){generation++;resize?.disconnect();resize=null;map?.remove();map=null;}
    function position(r){return r&&typeof r.latitude==='number'&&typeof r.longitude==='number'&&Number.isFinite(r.latitude)&&Number.isFinite(r.longitude)&&Math.abs(r.latitude)<=90&&Math.abs(r.longitude)<=180&&(r.latitude!==0||r.longitude!==0)?[r.latitude,r.longitude]:null;}
    function popup(selected,r){const box=document.createElement('div');box.append(text('strong',`${name(selected)} ${r.incoming&&r.outgoing?'↔':r.outgoing?'→':'←'} ${name(r)}`),text('p',`${name(selected)} → ${name(r)}: ${r.outgoing} receptions; ${r.outgoing_unique||0} unique packets`),text('p',`${name(r)} → ${name(selected)}: ${r.incoming} receptions; ${r.incoming_unique||0} unique packets`),text('p',`Last observation: ${stamp(r.last_observed)}`),text('p','A direction with no observations is not proof that communication is impossible.'),text('p','Relationships are inferred from observed flood routes, not verified direct RF links.'),text('p',`Public keys: ${selected.public_key} / ${r.public_key}`,'map-key'));return box;}
    async function neighborMap(data){
        const host=$('statistics-neighbor-map'),note=$('statistics-map-notes'),missing=$('statistics-missing-coordinates'),uncertain=$('statistics-ambiguous');if(!host)return;
        dispose();const ticket=generation;host.replaceChildren();note.replaceChildren();missing.replaceChildren();uncertain.replaceChildren();
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
            function marker(r,selectedMarker=false){const p=position(r);if(!p)return;points.push(p);const dot=text('span',selectedMarker?'S':'R',selectedMarker?'statistics-marker selected':'statistics-marker');L.marker(p,{icon:L.divIcon({html:dot,className:'statistics-map-icon',iconSize:[28,28],iconAnchor:[14,14]})}).addTo(layer).bindPopup(selectedMarker?text('strong',name(r)):popup(selected,r));}
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
        hourly(data);ranking('statistics-hops',data.hops,r=>`${r.hop_count} ${r.hop_count===1?'hop':'hops'}`,'Observed total route hop count');ranking('statistics-regions',data.regions,r=>r.name,'MeshCore regional traffic',true);neighborMap(data);
    }};
})();
