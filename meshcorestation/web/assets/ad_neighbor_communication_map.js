/* Saved Analyzer reach only: shared Leaflet loader, names and evidence semantics. */
(() => {
    const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n;};
    const coords=n=>n&&[n.lat,n.lon].every(v=>typeof v==='number'&&Number.isFinite(v))&&Math.abs(n.lat)<=90&&Math.abs(n.lon)<=180;
    const names=()=>window.MeshcoreStationRepeaterNames,relations=()=>window.MeshcoreStationNetworkRelationships;
    const value=v=>v==null?'Unknown':String(v);
    function neighbors(rows,key){
        const unique=new Map();
        for(const n of rows||[]){
            if(typeof n.role!=='string'||n.role.trim().toLowerCase()!=='repeater'||typeof n.pubkey!=='string'||!/^[a-f0-9]{64}$/i.test(n.pubkey)||n.pubkey.toLowerCase()===key)continue;
            const id=n.pubkey.toLowerCase(),old=unique.get(id);
            if(!old)unique.set(id,{...n,pubkey:id});
            else if(['weHear','theyHear','twoWay','confidence','lat','lon','distanceKm'].some(k=>old[k]!==n[k])){
                // Contradictory duplicate records cannot confirm direction or position.
                unique.set(id,{...old,weHear:null,theyHear:null,twoWay:null,confidence:null,lat:old.lat===n.lat?old.lat:null,lon:old.lon===n.lon?old.lon:null,distanceKm:old.distanceKm===n.distanceKm?old.distanceKm:null});
            }
        }
        return [...unique.values()];
    }
    function summary(rows){
        const counts={total:rows.length,bidirectional:0,unidirectional:0,unknown:0};
        for(const n of rows)counts[relations().describe(n).direction]++;
        return counts;
    }
    function create(snapshot,key,visible){
        const section=el('section',null,'stats-section');section.id='performance-neighbor-map';section.append(el('h3','Neighbor Communication Map'));
        let map=null,disposed=false,pending=false,observer=null,frame=null,layers=[],showLow=false;
        const rows=neighbors(snapshot?.available?snapshot.neighbors:[],key),counts=summary(rows),center=snapshot?.center;
        if(center)names().ingest([center,...rows],'analyzer');
        const stats=el('div',null,'stats-metrics performance-neighbor-statistics');
        for(const [label,field] of [['Total Neighbors','total'],['Two-Way Relationships','bidirectional'],['One-Way Relationships','unidirectional'],['Unknown/Insufficient Evidence','unknown']]){
            const card=el('div',null,'stats-metric');card.dataset.neighborStat=field;card.append(el('p',label,'muted'),el('strong',snapshot?.available?counts[field]:'Not available'));stats.append(card);
        }
        section.append(stats);
        const stamp=snapshot?.fetched_at;
        section.append(el('p',snapshot?.available?`Latest saved Analyzer reach: 24-hour observation window; retrieved ${window.meshcorestationFormatDate(stamp)}. This source has no saved 7-day or 30-day relationship map; the history selector does not widen this window.`:'No saved Analyzer relationship snapshot. Open Network Monitoring or wait for scheduled collection; unavailable data is not zero activity.','muted'));
        if(snapshot?.available&&Date.now()/1000-stamp>13*3600)section.append(el('p','Older saved snapshot; current external observations may be unavailable.','stats-message'));
        const label=el('label',null,'performance-neighbor-filter'),checkbox=el('input');checkbox.type='checkbox';checkbox.id='performance-neighbor-low';label.append(checkbox,document.createTextNode('Show low-confidence links'));section.append(label);
        section.append(el('p','Counts include all observed repeater neighbors. Low-confidence links are hidden initially; their markers and counts remain visible.','muted'));
        const legend=el('div',null,'network-map-legend');legend.setAttribute('aria-label','Neighbor communication legend');
        for(const [text,kind] of [['Green — Two-way observed communication','bidirectional'],['Red — One-way observed communication','unidirectional'],['Gray — Unknown direction','unknown'],['Dashed — Low confidence','low'],['Dotted — Unknown confidence','unreported']]){const row=el('div'),line=el('span',null,'network-line-sample '+kind);line.setAttribute('aria-hidden','true');row.append(line,document.createTextNode(text));legend.append(row);}section.append(legend,el('p',relations().explanation,'muted'));
        const note=el('p',snapshot?.available?'Loading saved neighbor map…':'Map unavailable until a successful Analyzer snapshot is saved.','stats-message');note.setAttribute('role','status');
        const canvas=el('div',null,'map-canvas performance-neighbor-canvas');canvas.setAttribute('aria-label','Geographical neighbor communication map');section.append(note,canvas);
        const missing=el('section',null,'performance-neighbor-missing');missing.append(el('h4','Neighbors without coordinates'));
        const absent=rows.filter(n=>!coords(n));if(!absent.length)missing.append(el('p',snapshot?.available?'None in this saved snapshot.':'No saved neighbor information.'));
        else{const list=el('ul');for(const n of absent){const item=el('li');item.append(names().element(n.pubkey));const r=relations().describe(n);item.append(el('span',` — ${r.observation} weHear: ${value(r.we)}; theyHear: ${value(r.they)}; confidence: ${r.confidence}.`));list.append(item);}missing.append(list);}section.append(missing);
        function popup(n,selected=false){
            const box=el('div',null,'network-connection-popup');box.append(names().element(selected?key:n.pubkey));
            if(selected)box.append(el('p','Selected repeater'));
            else{
                const r=relations().describe(n);box.append(el('p',r.observation));
                for(const [label,v] of [['Distance',typeof n.distanceKm==='number'&&Number.isFinite(n.distanceKm)&&n.distanceKm>=0?n.distanceKm+' km':'Unknown'],['weHear (selected repeater hears neighbor)',r.we],['theyHear (neighbor hears selected repeater)',r.they],['Analyzer confidence',r.confidence]])box.append(el('p',label+': '+value(v)));
                box.append(el('p','Missing observations do not prove that the reverse direction is impossible.'));
            }
            const keys=el('details');keys.append(el('summary','Public keys'),el('p','Selected repeater: '+key));if(!selected)keys.append(el('p','Neighbor: '+n.pubkey));box.append(keys,el('p',relations().explanation));return box;
        }
        const popupOptions=()=>({minWidth:120,maxWidth:Math.max(120,Math.min(300,canvas.clientWidth-110)),maxHeight:Math.max(150,canvas.clientHeight-95),autoPanPadding:[32,20]});
        function drawLinks(){
            if(!map)return;
            for(const layer of layers)map.removeLayer(layer);layers=[];
            if(!coords(center))return;
            for(const n of rows.filter(coords)){
                const r=relations().describe(n);if(r.confidence==='low'&&!showLow)continue;
                const points=[[center.lat,center.lon],[n.lat,n.lon]],common={dashArray:r.dashArray,opacity:1,lineCap:'round'};
                layers.push(L.polyline(points,{...common,color:'var(--panel)',weight:8,interactive:false,className:'network-relationship-halo'}).addTo(map));
                layers.push(L.polyline(points,{...common,color:r.color,weight:4,className:'network-relationship neighbor-direction-'+r.direction+' neighbor-confidence-'+r.confidence}).addTo(map).bindPopup(()=>popup(n),popupOptions()));
            }
        }
        function resize(){
            if(disposed||!visible()||!section.isConnected)return;
            if(!map){init();return;}
            if(frame!=null)window.cancelAnimationFrame(frame);
            frame=window.requestAnimationFrame(()=>{frame=null;if(!disposed&&visible())map?.invalidateSize({pan:false});});
        }
        function renamed(){names().refresh(section);if(map)map.eachLayer(layer=>{if(layer.getElement&&layer.options?.neighborKey)layer.getElement()?.setAttribute('title',names().label(layer.options.neighborKey));});}
        async function init(){
            if(disposed||pending||map||!snapshot?.available||!visible()||!section.isConnected)return;
            if(!coords(center)&&!rows.some(coords)){note.textContent='Map unavailable: no usable repeater coordinates. Neighbor details are listed below.';canvas.hidden=true;return;}
            pending=true;
            try{
                await window.meshcorestationLoadMapLibrary({clustering:false});
                if(disposed||!visible()||!section.isConnected)return;
                map=L.map(canvas,{maxZoom:19}).setView(coords(center)?[center.lat,center.lon]:[rows.find(coords).lat,rows.find(coords).lon],10);
                const points=[];
                function marker(n,selected){
                    const id=selected?key:n.pubkey,span=el('span',selected?'S':'R','map-marker'+(selected?' performance-neighbor-selected':''));if(!selected)span.style.background=relations().describe(n).color;
                    const pos=[n.lat,n.lon];points.push(pos);
                    L.marker(pos,{icon:L.divIcon({className:'route-marker-icon',html:span,iconSize:[28,28],iconAnchor:[14,14]}),title:names().label(id),neighborKey:id,zIndexOffset:selected?100:0}).addTo(map).bindPopup(()=>popup(n,selected),popupOptions());
                }
                if(coords(center))marker(center,true);for(const n of rows.filter(coords))marker(n,false);
                drawLinks();if(points.length>1)map.fitBounds(points,{padding:[24,24],maxZoom:13,animate:false});
                note.textContent=coords(center)?'Saved observations only. Zoom, pan or select a marker for details.':'Selected repeater coordinates unavailable; located neighbors are shown without connecting lines.';
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).on('tileerror',()=>{if(!disposed)note.textContent='Background tiles unavailable; saved markers and available relationship lines remain visible.';}).addTo(map);
                resize();
            }catch(e){if(!disposed){map?.remove();map=null;note.textContent='Neighbor map unavailable: '+(e.message||String(e));}}
            finally{pending=false;}
        }
        checkbox.onchange=()=>{showLow=checkbox.checked;drawLinks();};
        if(window.ResizeObserver){observer=new ResizeObserver(resize);observer.observe(canvas);}
        window.addEventListener('resize',resize);document.addEventListener('repeater-names-updated',renamed);
        queueMicrotask(init);
        return {element:section,resize,dispose(){disposed=true;observer?.disconnect();window.removeEventListener('resize',resize);document.removeEventListener('repeater-names-updated',renamed);if(frame!=null)window.cancelAnimationFrame(frame);map?.remove();map=null;}};
    }
    window.MeshcoreStationNeighborMap={create,neighbors,summary};
})();
