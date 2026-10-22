/* The server owns the managed list; this browser remembers only the viewed repeater. */
(() => {
    const storageKey='meshcorestation.managed-repeaters';
    const $=id=>document.getElementById(id);
    let known=[],managed=[],attached=false;
    function persist(){
        try{localStorage.setItem(storageKey,JSON.stringify({keys:managed,selected:window.meshcorestationSelectedRepeater}));}
        catch{$('managed-repeater-message').textContent='Browser storage unavailable; the managed list is saved on the server, but the viewed repeater will not be remembered.';}
    }
    function select(key){
        if(!key){
            window.meshcorestationSelectedRepeater='';
            $('managed-repeater').replaceChildren(new Option('Add a repeater from the map',''));
            $('managed-repeater-open').disabled=true;$('managed-repeater-remove').disabled=true;
            $('open-voltage').disabled=true;persist();
            document.dispatchEvent(new CustomEvent('managed-repeater-selected',{detail:''}));return;
        }
        if(!known.some(r=>r.public_key===key))return;
        if(!managed.includes(key))return;
        window.meshcorestationSelectedRepeater=key;
        const picker=$('managed-repeater');picker.replaceChildren();
        for(const value of managed){const r=known.find(r=>r.public_key===value);if(r)picker.add(new Option(`${r.name||'(unnamed)'} · ${value.slice(0,12)}`,value));}
        picker.value=key;$('managed-repeater-open').disabled=false;$('managed-repeater-remove').disabled=false;$('open-voltage').disabled=false;
        persist();document.dispatchEvent(new CustomEvent('managed-repeater-selected',{detail:key}));
    }
    async function load(preferredKey){
        try{
            const response=await fetch('/api/bot/voltage?days=1',{headers:{'X-Meshcore-Control':'1'},cache:'no-store'});
            const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Could not load repeaters.');
            known=data.repeaters;let saved={};
            try{saved=JSON.parse(localStorage.getItem(storageKey)||'{}')||{};}catch{}
            managed=(Array.isArray(data.managed_repeaters)?data.managed_repeaters:[]).filter((key,i,keys)=>known.some(r=>r.public_key===key)&&keys.indexOf(key)===i);
            const initial=managed.includes(preferredKey)?preferredKey:managed.includes(saved.selected)?saved.selected:managed[0]||'';
            if(initial&&known.some(r=>r.public_key===initial))select(initial);
            else select('');
            return true;
        }catch(error){$('managed-repeater-message').textContent=error.message;return false;}
    }
    function attach(){
        if(attached||!$('managed-repeater'))return;attached=true;
        $('managed-repeater').onchange=()=>select($('managed-repeater').value);
        $('managed-repeater-add').onclick=()=>document.dispatchEvent(new CustomEvent('stats-picker-open',{detail:{repeaters:known,selected:window.meshcorestationSelectedRepeater||'',managedRepeaters:managed.slice(),selectionEvent:'managed-repeater-added',title:'Add repeater from map',actionLabel:'Add repeater'}}));
        $('managed-repeater-open').onclick=()=>{const r=known.find(r=>r.public_key===window.meshcorestationSelectedRepeater);if(r)window.meshcorestationManageRepeater({...r,type:2});};
        $('managed-repeater-remove').onclick=async()=>{
            const key=window.meshcorestationSelectedRepeater;
            const name=known.find(r=>r.public_key===key)?.name||key;
            if(!key||!window.confirm(`Remove ${name} from management? Its battery settings, readings, report history and collected statistics will be permanently deleted.`))return;
            $('managed-repeater-remove').disabled=true;
            try{
                const response=await fetch('/api/bot/voltage',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},body:JSON.stringify({operation:'remove',public_key:key})});
                const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'Could not remove repeater.');
                try{localStorage.removeItem('meshcorestation.repeater.password.'+key.toLowerCase());}catch{}
                if(!await load())throw Error('Removal was submitted, but the managed list could not be refreshed. Reload the page to verify it.');
                if(managed.includes(key))throw Error('Removal could not be verified. Reload and try again.');
                $('managed-repeater-message').textContent='Repeater removed and its monitoring data deleted.';
            }catch(error){$('managed-repeater-message').textContent=error.message;$('managed-repeater-remove').disabled=false;}
        };
        document.addEventListener('managed-repeater-added',async e=>{
            if(managed.includes(e.detail)){$('managed-repeater-message').textContent='This repeater is already managed.';return;}
            $('managed-repeater-message').textContent='Adding repeater…';
            try{
                const response=await fetch('/api/bot/voltage',{method:'POST',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},body:JSON.stringify({operation:'add',public_key:e.detail})});
                const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'Could not add repeater.');
                if(!await load(e.detail))throw Error('Addition was submitted, but the managed list could not be refreshed.');
                if(!managed.includes(e.detail))throw Error('Addition could not be verified. Reload and try again.');
                $('managed-repeater-message').textContent='Repeater added. Battery monitoring can be enabled in its settings.';
            }catch(error){$('managed-repeater-message').textContent=error.message;}
        });
        // Avoid this extra voltage/repeater request while management is collapsed.
        const disclosure=$('repeater-management-disclosure');
        if(disclosure){
            disclosure.addEventListener('toggle',()=>{if(disclosure.open&&!known.length)load();});
            if(disclosure.open)load();
        }
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
