(() => {
    let dialog,map,clusters,controller,repeaters=[],selected='',selectionEvent='stats-picker-selected',actionLabel='Use this repeater',managedRepeaters=new Set(),markers=new Map();
    const el=(tag,value,cls)=>{const n=document.createElement(tag);if(value!=null)n.textContent=value;if(cls)n.className=cls;return n;};
    function choose(repeater){
        if(managedRepeaters.has(repeater.public_key))return;
        dialog.close();
        document.dispatchEvent(new CustomEvent(selectionEvent,{detail:repeater.public_key}));
    }
    function action(repeater){
        const managed=managedRepeaters.has(repeater.public_key);
        const button=el('button',managed?'Already managed':actionLabel);
        button.type='button';button.disabled=managed;
        if(managed)button.title='This repeater is already in management.';
        button.onclick=()=>choose(repeater);
        return button;
    }
    function details(repeater){
        const box=el('div');box.append((window.MeshcoreStationRepeaterNames?.element(repeater.public_key,'strong')||el('strong',repeater.name)),el('p',repeater.public_key,'map-key'));
        box.append(action(repeater));window.meshcorestationRepeaterActions(box,repeater,()=>dialog.close());return box;
    }
    function filter(){
        const query=dialog.querySelector('.stats-map-search').value.trim().toLowerCase();
        const list=dialog.querySelector('.stats-map-list');list.replaceChildren();
        window.MeshcoreStationRepeaterNames?.ingest(repeaters);
        const matches=repeaters.filter(r=>`${r.name} ${r.public_key}`.toLowerCase().includes(query));
        for(const repeater of matches){
            const row=el('div',null,'stats-picker-row');
            row.append((window.MeshcoreStationRepeaterNames?.element(repeater.public_key,'strong')||el('strong',repeater.name+(repeater.public_key===selected?' (selected)':''))),el('span',repeater.public_key,'map-key'));
            const marker=markers.get(repeater.public_key);
            if(marker){const locate=el('button','Show on map');locate.type='button';locate.onclick=()=>{const currentMap=map;window.meshcorestationRevealMarker(map,clusters,marker,()=>map===currentMap&&dialog.open);};row.append(locate);}
            else row.append(el('span','No map position available','muted'));
            row.append(action(repeater));list.append(row);
        }
        if(!matches.length)list.append(el('p','No repeaters match this search.'));
        if(query)dialog.querySelector('.stats-map-fallback').open=true;
    }
    async function open(detail){
        if(!dialog){
            dialog=el('dialog');dialog.id='stats-repeater-picker';dialog.setAttribute('aria-labelledby','stats-picker-title');
            dialog.innerHTML='<div class="dialog-header"><h2 id="stats-picker-title">Choose my repeater</h2><button type="button" class="stats-picker-close" aria-label="Close repeater picker">×</button></div><p>Click a repeater marker, check its name and public key, then choose Use this repeater. Closing leaves your selection unchanged.</p><label>Search name or public key<input class="stats-map-search" type="search" placeholder="Find your repeater"></label><p class="stats-picker-message" role="status" aria-live="polite"></p><div class="stats-picker-map map-canvas" role="region" aria-label="Repeater selection map"></div><details class="stats-map-fallback"><summary>Searchable repeater list / repeaters without coordinates</summary><div class="stats-map-list"></div></details>';
            window.meshcorestationPrepareDialog(dialog);document.body.append(dialog);
            dialog.querySelector('.stats-picker-close').onclick=()=>dialog.close();
            dialog.querySelector('.stats-map-search').oninput=filter;
            dialog.addEventListener('close',()=>{controller?.abort();if(map){map.remove();map=null;}markers.clear();});
        }
        controller?.abort();if(map){map.remove();map=null;}markers.clear();
        actionLabel=detail.actionLabel||'Use this repeater';
        dialog.querySelector('p').textContent=`Click a repeater marker, check its name and public key, then choose ${actionLabel}. ${detail.managedRepeaters?'Already managed repeaters cannot be added twice. ':''}Closing leaves your selection unchanged.`;
        repeaters=detail.repeaters;selected=detail.selected;selectionEvent=detail.selectionEvent||'stats-picker-selected';
        managedRepeaters=new Set(detail.managedRepeaters||[]);
        dialog.querySelector('#stats-picker-title').textContent=detail.title||'Choose my repeater';
        dialog.querySelector('.stats-map-search').value='';dialog.querySelector('.stats-map-fallback').open=false;
        const message=dialog.querySelector('.stats-picker-message');message.textContent='Loading known repeater positions…';
        dialog.showModal();filter();dialog.querySelector('.stats-picker-close').focus();
        const request=new AbortController();controller=request;
        try{
            const [response] = await Promise.all([
                fetch('/api/maps/repeaters', {cache:'no-store',signal:request.signal}),
                (!window.L || !window.L.markerClusterGroup) ? window.meshcorestationLoadMapLibrary({clustering:true}) : Promise.resolve()
            ]);
            const data=await response.json();if(!response.ok)throw Error(data.error||'Could not load repeater positions.');
            if(request.signal.aborted || !dialog.open)return;
            if(!window.L)throw Error('Map library unavailable. Use the searchable list.');
            map=L.map(dialog.querySelector('.stats-picker-map'));
            // Avoid downloading tiles for Germany before navigating to the selected repeater.
            const knownKeys=new Set(repeaters.map(r=>r.public_key));
            const initial=data.nodes.filter(node=>node.role==='repeater'&&knownKeys.has(node.public_key));
            const picked=initial.find(node=>node.public_key===selected);
            if(picked)map.setView(picked.position,12);
            else if(initial.length)map.fitBounds(initial.map(node=>node.position),{padding:[30,30],maxZoom:13});
            else map.setView([51,10],5);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'}).on('tileerror',()=>{message.textContent='Map tiles unavailable. Markers and the searchable list remain usable.';}).addTo(map);
            clusters=window.meshcorestationMarkerClusters(map);
            const positions=[];
            for(const node of data.nodes){
                const repeater=repeaters.find(r=>r.public_key===node.public_key);
                if(node.role!=='repeater'||!repeater)continue;
                const chosen=repeater.public_key===selected;
                const badge=el('span','R','map-marker repeater'+(chosen?' stats-selected-marker':''));
                const icon=L.divIcon({html:badge,className:'map-icon',iconSize:[28,28],iconAnchor:[14,14]});
                const marker=L.marker(node.position,{icon,title:(window.MeshcoreStationRepeaterNames?.label(repeater.public_key)||repeater.name)+(chosen?' (selected)':''),zIndexOffset:chosen?100:0}).addTo(clusters).bindPopup(() => details({...node,...repeater}));
                markers.set(repeater.public_key,marker);positions.push(node.position);
            }
            filter();message.textContent=`${markers.size} of ${repeaters.length} repeaters shown. Zoom in or click numbered groups to expand them. Use the list for missing positions.`;
            if(!markers.size)dialog.querySelector('.stats-map-fallback').open=true;
            const currentMap=map;
            requestAnimationFrame(()=>{
                if(map!==currentMap)return;
                map.invalidateSize();
                const current=markers.get(selected);
                if(current)window.meshcorestationRevealMarker(map,clusters,current,()=>map===currentMap&&dialog.open);
            });
        }catch(error){if(request.signal.aborted)return;message.textContent=error.message;dialog.querySelector('.stats-map-fallback').open=true;}
    }
    document.addEventListener('stats-picker-open',event=>open(event.detail));
})();
