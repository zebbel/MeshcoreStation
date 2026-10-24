/* Experimental, on-demand external observations. No interval or background poll. */
(() => {
    let attached=false, controller=null, generation=0, current='', map=null, pendingKey=null, mapRender=0, mapObserver=null, resizeHandler=null, resizeFrame=null, mapIdentityHandler=null;
    const cache=new Map(),$=id=>document.getElementById(id);
    const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n;};
    const date=v=>v==null?'Unknown':window.meshcorestationFormatDate(typeof v==='string'&&/^\d{4}-/.test(v)?new Date(v):v,'Europe/Berlin');
    const val=v=>v==null?'Unknown':String(v);
    const visible=()=>$('repeater-network-disclosure')?.open && $('repeater-optimizer-disclosure')?.open!==false;
    const names=()=>window.MeshcoreStationRepeaterNames;
    const identity=key=>names().element(key);
    function dispose(){
        ++mapRender;if(mapIdentityHandler)document.removeEventListener('repeater-names-updated',mapIdentityHandler);mapIdentityHandler=null;mapObserver?.disconnect();mapObserver=null;
        if(resizeHandler)window.removeEventListener('resize',resizeHandler);resizeHandler=null;
        if(resizeFrame!=null)window.cancelAnimationFrame?.(resizeFrame);resizeFrame=null;
        if(map){map.remove();map=null;}
    }
    function invalidate(){++generation;controller?.abort();controller=null;pendingKey=null;dispose();$('network-content')?.replaceChildren();$('network-content')?.setAttribute('aria-busy','false');}
    function table(title,headers,rows){
        const box=el('section',null,'stats-section');box.append(el('h3',title));
        if(!rows.length){box.append(el('p','No observations returned for this capture window.'));return box;}
        const wrap=el('div',null,'stats-table-scroll'),t=el('table'),head=el('tr');headers.forEach(x=>head.append(el('th',x)));const thead=el('thead');thead.append(head);t.append(thead);if(headers.length>=4)t.classList.add('stats-wide-table');
        const body=el('tbody');for(const row of rows){const tr=el('tr');row.forEach(v=>{const td=el('td');if(v instanceof Node)td.append(v);else td.textContent=val(v);tr.append(td);});body.append(tr);}t.append(body);wrap.append(t);box.append(wrap);return box;
    }
    function chart(title,points){
        const box=el('section',null,'stats-section');box.append(el('h3',title));
        if(!points.length){box.append(el('p','No historical buckets returned.'));return box;}
        const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('class','stats-chart');svg.setAttribute('viewBox','0 0 800 180');svg.setAttribute('role','img');svg.setAttribute('aria-label',title);
        const max=Math.max(1,...points.map(p=>Number(p.count)||0)),width=760/points.length;
        points.forEach((p,i)=>{const b=document.createElementNS(ns,'rect'),h=140*(Number(p.count)||0)/max;for(const [k,v] of Object.entries({x:20+i*width,y:150-h,width:Math.max(1,width-2),height:h,fill:'var(--accent)'}))b.setAttribute(k,v);const title=document.createElementNS(ns,'title');title.textContent=`${date(p.bucket)}: ${val(p.count)}`;b.append(title);svg.append(b);});box.append(svg);
        const details=el('details');details.append(el('summary','Show historical values'),table('Buckets',['Time','Count'],points.map(p=>[date(p.bucket),p.count])));box.append(details);return box;
    }
    function status(r){
        const stamp=r.fetched_at?`Last successful retrieval: ${date(r.fetched_at)}. `:'';
        $('network-status').textContent=`Experimental · live integration unverified. ${r.error||''} ${stamp}${r.data?(r.stale?'Stale saved snapshot.':'Five-minute snapshot cache.'):r.state==='empty'?'No saved snapshot.':''}`;
        $('network-status').dataset.state=r.state;
    }
    async function drawMap(data,host,id,key){
        const version=mapRender,center=data.detail.node,neighbors=data.reach.neighbourList;
        const coords=n=>typeof n.lat==='number'&&typeof n.lon==='number'&&Math.abs(n.lat)<=90&&Math.abs(n.lon)<=180;
        if(!coords(center)){host.append(el('p','Map unavailable: no usable selected-repeater coordinates.'));return;}
        const note=el('p','Loading observation map…');host.append(note);
        try{
            await window.meshcorestationLoadMapLibrary({clustering:false});
            if(id!==generation||version!==mapRender||!visible()||key!==current)return;
            const canvas=el('div',null,'map-canvas network-map');host.append(canvas);map=window.L.map(canvas,{maxZoom:19}).setView([center.lat,center.lon],10);
            const points=[[center.lat,center.lon]],markers=[];
            const popup=(key,inferred)=>{
                const box=el('div');box.append(identity(key));
                if(inferred)box.append(el('p','Analyzer-derived relationship; direct RF unverified.'));
                return box;
            };
            function marker(pos,key,selected){
                const icon=L.divIcon({className:'route-marker-icon',html:el('span',selected?'S':'R',selected?'map-marker bot':'map-marker'),iconSize:[28,28],iconAnchor:[14,14]});
                markers.push({key,layer:L.marker(pos,{icon,title:names().label(key),zIndexOffset:selected?100:0}).addTo(map).bindPopup(()=>popup(key,!selected))});
            }
            marker(points[0],key,true);
            const seen=new Set([key]);
            for(const n of neighbors.filter(coords)){
                if(seen.has(n.pubkey))continue;seen.add(n.pubkey);
                const pos=[n.lat,n.lon];points.push(pos);marker(pos,n.pubkey,false);
                if(n.weHear>0||n.theyHear>0||n.twoWay===true){
                    const common={dashArray:'7 6',opacity:.95,lineCap:'round',interactive:false};
                    L.polyline([points[0],pos],{...common,color:'var(--panel)',weight:7,className:'network-relationship-halo'}).addTo(map);
                    L.polyline([points[0],pos],{...common,color:'var(--accent)',weight:3,className:'network-relationship'}).addTo(map);
                }
            }
            if(points.length>1)map.fitBounds(points,{padding:[20,20],maxZoom:13,animate:false});
            mapIdentityHandler=()=>{for(const m of markers)m.layer.getElement?.()?.setAttribute('title',names().label(m.key));};
            document.addEventListener('repeater-names-updated',mapIdentityHandler);
            const activeMap=map;
            resizeHandler=()=>{
                if(resizeFrame!=null)window.cancelAnimationFrame?.(resizeFrame);
                resizeFrame=window.requestAnimationFrame(()=>{resizeFrame=null;if(map===activeMap&&version===mapRender&&visible())activeMap.invalidateSize({pan:false});});
            };
            if(window.ResizeObserver){mapObserver=new ResizeObserver(resizeHandler);mapObserver.observe(canvas);}
            window.addEventListener('resize',resizeHandler);resizeHandler();
            const tiles=window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'});
            tiles.on('tileerror',()=>{note.textContent='Background tiles unavailable; observation markers remain visible.';});tiles.addTo(map);
            note.textContent='Dashed lines show analyzer-derived relationships, not verified direct RF links.';
        }catch(e){if(id===generation)note.textContent='Observation map unavailable: '+(e.message||String(e));}
    }
    function route(path){
        const box=el('span',null,'network-route');box.title=path.join(' → ');
        path.forEach((key,i)=>{if(i)box.append(document.createTextNode(' → '));box.append(identity(key));});return box;
    }
    function render(r,id,key){
        names().ingest(r.repeaters||[]);status(r);dispose();const host=$('network-content');host.replaceChildren();if(!r.data)return;
        const d=r.data,detail=d.detail,s=detail.stat,reach=d.reach;
        names().ingest(r.repeaters||[]);names().ingest([detail.node,...d.neighbors,...reach.neighbourList,...detail.relayNeighbours],'analyzer');
        const heading=el('p',null,'network-identity');heading.append(document.createTextNode('Analyzer snapshot for '),identity(key));host.append(heading);
        if($('network-selected'))$('network-selected').replaceChildren(identity(key));
        const cards=el('div',null,'stats-metrics');for(const [label,value] of [['Relayed packets / rolling 24h',s.relayCount24h],['Relayed packets / rolling 1h',s.relayCount1h],['Pairs served',s.pairsServed],['Graph degree',d.metrics.degree],['Directional neighbors',reach.neighbours],['Two-way inferred neighbors',reach.twoWayCount],['Direct observers',reach.directObservers]]){const card=el('div',null,'stats-metric');card.append(el('p',label,'muted'),el('strong',val(value)));cards.append(card);}host.append(cards);
        host.append(el('p','Rolling counts are replaced on refresh, never accumulated. Graph metrics and directional counts are not signal quality. Path prefixes may be ambiguous. Observer signal measurements describe the final hop only.','muted'));
        host.append(table('Directional reachability (analyzer-derived)',['Repeater','Distance km','Confidence','weHear','theyHear','Two-way'],reach.neighbourList.map(n=>[identity(n.pubkey),n.distanceKm,n.confidence,n.weHear,n.theyHear,n.twoWay==null?null:n.twoWay?'Yes':'No'])));
        host.append(table('Inferred neighbors',['Repeater','Distance km','Confidence','Provenance','SNR'],d.neighbors.map(n=>[identity(n.ID),n.DistanceKm,n.Conf,n.Provenance,n.SNR])));
        host.append(chart('Hourly relay activity',detail.relayTimeline),chart('Historical receptions',detail.timeline));
        host.append(table('Packet path patterns (potential hash ambiguity)',['Hop sequence','Count','Last seen'],detail.pathsThroughNode.map(p=>[route(p.path),p.count,date(p.lastSeen)])));
        host.append(table('Forwarding participation',['Neighbor','To','From','Total'],detail.relayNeighbours.map(p=>[identity(p.pubkey),p.toCount,p.fromCount,p.total])));
        host.append(table('Advertisement history',['Packet hash','Type','First seen'],detail.recentPackets.map(p=>[p.hash,p.packetType,date(p.firstSeen)])));
        host.append(table('Network metrics',['Metric','Value'],Object.entries(d.metrics).map(([field,value])=>[field,field==='id'?identity(value):value])));
        host.append(table('Clock evidence — counts only, no observer identities',['Packet hash','Observer count','Heard at'],d.clock.recentHashEvidence.map(p=>[p.hash,p.observers,date(p.heardAt)])));
        host.append(el('p',`Clock samples: ${val(d.clock.sampleCount)} · Direct packet rows: ${d.direct.rows.length} · Beacons: ${d.beacons.beacons.length} · Sensor readings: ${d.sensors.readings.length}. Empty successful responses are not access failures.`));
        host.append(table('Receiving observer evidence',['Field','Captured value'],detail.heardBy.map(p=>['Observer record',JSON.stringify(p)])));
        const mapHost=el('section',null,'stats-section');mapHost.append(el('h3','Observable relationships'));host.append(mapHost);drawMap(d,mapHost,id,key);
    }
    async function load(force=false){
        if(!visible())return;
        await window.meshcorestationEnsureRepeaterSelection?.();
        if(!visible())return;
        const key=window.meshcorestationSelectedRepeater||'';
        const identity=$('network-selected');
        if(identity){identity.replaceChildren(key?names().element(key):document.createTextNode('No repeater selected'));identity.title=key;}
        if(!key){invalidate();$('network-status').textContent='Select a repeater in Repeater Management.';return;}
        if(pendingKey===key)return;
        invalidate();current=key;pendingKey=key;const id=generation;
        controller=new AbortController();const requestController=controller,signal=controller.signal;
        let timedOut=false;const timeout=setTimeout(()=>{timedOut=true;requestController.abort();},35000);
        $('network-refresh').disabled=true;$('network-content').setAttribute('aria-busy','true');
        const saved=cache.get(key);if(saved)render(saved,id,key);else {$('network-status').dataset.state='loading';$('network-status').textContent='Loading saved external snapshot…';}
        async function request(query){
            const response=await fetch('/api/repeater-network?public_key='+encodeURIComponent(key)+query,{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal});
            const r=await response.json();if(!response.ok||!r.ok)throw Error(r.error||'Monitoring request failed.');
            if(r.public_key!==key)throw Error('Monitoring returned a different repeater.');
            return r;
        }
        const active=()=>id===generation&&current===key&&visible();
        try{
            let r=await request('&cache_only=1');if(!active())return;cache.set(key,r);render(r,id,key);
            if(force||r.stale){
                $('network-status').textContent+=' Refreshing external observations…';
                r=await request(force?'&refresh=1':'');if(!active())return;cache.set(key,r);render(r,id,key);
            }
        }catch(e){if(active()&&(e.name!=='AbortError'||timedOut)){$('network-status').dataset.state='unavailable';$('network-status').textContent='External monitoring unavailable: '+(timedOut?'request timed out.':e.message)+(cache.get(key)?.data?' Saved snapshot retained.':' No network activity conclusion can be drawn.');}}
        finally{clearTimeout(timeout);if(id===generation){pendingKey=null;controller=null;$('network-refresh').disabled=false;$('network-content').setAttribute('aria-busy','false');}}
    }
    function attach(){
        if(attached||!$('network-content'))return;attached=true;
        const toggle=()=>{if(visible())load();else{++generation;controller?.abort();controller=null;pendingKey=null;$('network-refresh').disabled=false;dispose();}};
        $('repeater-network-disclosure').addEventListener('toggle',toggle);
        $('repeater-optimizer-disclosure')?.addEventListener('toggle',toggle);
        document.addEventListener('managed-repeater-removed',e=>cache.delete(e.detail));
        document.addEventListener('managed-repeater-selected',()=>{invalidate();current=window.meshcorestationSelectedRepeater||'';if(visible())load();});
        $('network-refresh').onclick=()=>load(true);
        if(visible())load();
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
