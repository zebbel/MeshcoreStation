/* Passive analysis is independent of the administrator-only management bridge. */
(() => {
    let attached=false,frame=null,selected='';
    const $=id=>document.getElementById(id);
    const visible=()=>$('optimization-analysis-disclosure')?.open&&$('repeater-optimizer-disclosure')?.open;
    function post(data){frame?.contentWindow?.postMessage(data,location.origin);}
    function theme(){
        const styles=getComputedStyle(document.documentElement),palette={};
        for(const name of ['--bg','--panel','--text','--muted','--border','--accent','--soft','--green','--red','--shadow','--control-radius','--control-padding'])palette[name]=styles.getPropertyValue(name);
        post({type:'meshcorestation-optimizer-theme',palette});
    }
    function context(){if(visible()){theme();post({type:'meshcorestation-optimizer-context',public_key:selected,name:$('managed-repeater')?.selectedOptions[0]?.textContent||'Repeater'});}}
    async function load(){
        if(!visible())return;
        await window.meshcorestationEnsureRepeaterSelection?.();if(!visible())return;
        selected=window.meshcorestationSelectedRepeater||'';
        if(!selected){$('optimization-analysis-inline').replaceChildren();frame=null;return;}
        frame=$('repeater-advisor-frame');
        if(!frame){frame=document.createElement('iframe');frame.id='repeater-advisor-frame';frame.title='Optimization Analysis';$('optimization-analysis-inline').append(frame);}
        if(!frame.hasAttribute('src'))frame.src='/repeater-optimizer';else context();
    }
    function attach(){
        if(attached||!$('optimization-analysis-inline'))return;attached=true;
        const toggle=()=>{if(visible())load();else post({type:'meshcorestation-optimizer-pause'});};
        $('optimization-analysis-disclosure').addEventListener('toggle',toggle);$('repeater-optimizer-disclosure').addEventListener('toggle',toggle);
        document.addEventListener('managed-repeater-selected',()=>{
            selected=window.meshcorestationSelectedRepeater||'';
            // Recreate only the analysis document on selection, so no old repeater data survives.
            if(frame){frame.remove();frame=null;}
            if(visible())load();
        });
        $('analysis-connect').onclick=async()=>{
            await window.meshcorestationEnsureRepeaterSelection?.();
            const key=window.meshcorestationSelectedRepeater;if(!key)return;
            document.dispatchEvent(new CustomEvent('analysis-connect',{detail:{public_key:key,name:$('managed-repeater')?.selectedOptions[0]?.textContent||key,type:2}}));
        };
        $('analysis-disconnect').onclick=()=>document.dispatchEvent(new CustomEvent('analysis-disconnect'));
    }
    window.addEventListener('message',event=>{
        if(event.origin!==location.origin||!frame||event.source!==frame.contentWindow)return;
        if(event.data?.type==='meshcorestation-optimizer-ready')context();
        if(event.data?.type==='meshcorestation-optimizer-height'){
            const height=event.data.height;
            if(typeof height==='number'&&Number.isFinite(height)&&height>0&&height<=1000000)frame.style.height=Math.ceil(height)+'px';
        }
    });
    window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change',theme);
    new MutationObserver(()=>{if(visible())theme();}).observe(document.documentElement,{attributes:true,attributeFilter:['class','style','data-theme']});
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
