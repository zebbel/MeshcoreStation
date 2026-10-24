/* Shared display identities. Exact keys only; no requests and no prefix guessing. */
(() => {
    const records=new Map(),byName=new Map();let queued=false,revision=0;
    const keyOf=r=>typeof r==='string'?r:r?.public_key||r?.pubkey||r?.ID||r?.id||r?.key;
    const full=k=>typeof k==='string'&&/^[a-f0-9]{64}$/i.test(k);
    const normalize=k=>typeof k==='string'?k.trim().toLowerCase():'';
    function validName(name,key){return typeof name==='string'&&name.trim()&&!/^(unknown(?: repeater)?|\(unnamed\)|unnamed(?: repeater)?)$/i.test(name.trim())&&normalize(name)!==key&&!/^[0-9a-f]{8,64}$/i.test(name.trim());}
    function ingest(items,source='local'){
        let changed=false;const priority=source==='local'?30:source==='analyzer'?20:10;
        for(const r of items||[]){const key=normalize(keyOf(r)),name=r?.name??r?.Name??r?.label;
            if(!full(key)||!validName(name,key))continue;
            const previous=records.get(key),clean=name.trim().normalize('NFC');
            if(previous&&previous.priority>priority)continue;
            if(previous?.name===clean&&previous.priority===priority)continue;
            if(previous){const group=byName.get(previous.name.toLocaleLowerCase());group?.delete(key);}
            const index=clean.toLocaleLowerCase();if(!byName.has(index))byName.set(index,new Set());byName.get(index).add(key);
            records.set(key,{name:clean,priority});changed=true;
        }
        if(changed){++revision;if(!queued){queued=true;queueMicrotask(()=>{queued=false;refresh();document.dispatchEvent(new CustomEvent('repeater-names-updated',{detail:revision}));});}}
    }
    function suffix(key,others){let size=8;while(size<64&&others.some(k=>k!==key&&k.slice(0,size)===key.slice(0,size)))size+=4;return key.slice(0,size)+(size<64?'…':'');}
    function resolve(value){
        const key=normalize(keyOf(value)),record=records.get(key);
        if(!full(key))return {key,label:`Unknown Repeater (${key.slice(0,8)||'?'}…) · unresolved prefix`,status:'unresolved'};
        if(!record)return {key,label:`Unknown Repeater (${key.slice(0,8)}…)`,status:'unknown'};
        const duplicates=[...byName.get(record.name.toLocaleLowerCase())];
        return {key,label:record.name+(duplicates.length>1?' ('+suffix(key,duplicates)+')':''),status:'named'};
    }
    function apply(node){const r=resolve(node.dataset.repeaterKey);node.textContent=r.label;node.title=r.key+(r.status==='unresolved'?' — unresolved prefix; identity not confirmed':'');node.dataset.identityStatus=r.status;}
    function element(value,tag='span'){
        const node=document.createElement(tag);node.dataset.repeaterKey=normalize(keyOf(value));apply(node);return node;
    }
    function refresh(root=document){for(const n of root.querySelectorAll('[data-repeater-key]'))apply(n);}
    window.MeshcoreStationRepeaterNames={ingest,resolve,entries:()=>[...records].map(([public_key,r])=>({public_key,name:r.name})),label:value=>resolve(value).label,element,refresh};
})();
