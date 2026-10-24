/* Passive analysis is independent of the administrator-only management bridge. */
(() => {
    let attached=false,frame=null,selected='';
    const $=id=>document.getElementById(id);
    const visible=()=>$('optimization-analysis-disclosure')?.open&&$('repeater-optimizer-disclosure')?.open;
    function post(data){frame?.contentWindow?.postMessage(data,location.origin);}
    function theme(){
        const styles=getComputedStyle($('optimization-analysis-inline')||document.documentElement),palette={};
        // Match the reference's visible surface, including locally overridden themes.
        let surfaceNode=$('repeater-statistics-inline'),surface='';
        while(surfaceNode){const color=getComputedStyle(surfaceNode).backgroundColor;if(color&&color!=='transparent'&&color!=='rgba(0, 0, 0, 0)'){surface=color;break;}surfaceNode=surfaceNode.parentElement;}
        palette['--optimizer-surface']=surface||styles.getPropertyValue('--panel');
        if(frame)frame.style.backgroundColor=palette['--optimizer-surface'];
        for(const name of ['--bg','--panel','--text','--muted','--border','--accent','--soft','--green','--red','--shadow','--control-radius','--control-padding'])palette[name]=styles.getPropertyValue(name);
        post({type:'meshcorestation-optimizer-theme',palette,color_scheme:styles.colorScheme});
    }
    function context(){if(visible()){theme();post({type:'meshcorestation-optimizer-context',public_key:selected,name:window.MeshcoreStationRepeaterNames?.label(selected)||$('managed-repeater')?.selectedOptions[0]?.textContent||'Repeater',repeaters:window.MeshcoreStationRepeaterNames?.entries()||[]});}}
    async function load(){
        if(!visible())return;
        await window.meshcorestationEnsureRepeaterSelection?.();if(!visible())return;
        selected=window.meshcorestationSelectedRepeater||'';
        if(!selected){$('optimization-analysis-inline').replaceChildren();frame=null;return;}
        frame=$('repeater-advisor-frame');
        if(!frame){frame=document.createElement('iframe');frame.id='repeater-advisor-frame';frame.title='Optimization Analysis';frame.addEventListener('load',theme);$('optimization-analysis-inline').append(frame);theme();}
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
    document.addEventListener('repeater-names-updated',()=>{if(visible())post({type:'meshcorestation-optimizer-names',repeaters:window.MeshcoreStationRepeaterNames.entries()});});
    window.addEventListener('message',event=>{
        if(event.origin!==location.origin||!frame||event.source!==frame.contentWindow)return;
        if(event.data?.type==='meshcorestation-optimizer-ready')context();
        if(event.data?.type==='meshcorestation-optimizer-height'){
            const height=event.data.height;
            if(typeof height==='number'&&Number.isFinite(height)&&height>0&&height<=1000000)frame.style.height=Math.ceil(height)+'px';
        }
    });
    window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change',theme);
    const themeObserver=new MutationObserver(()=>{if(visible())theme();});
    for(const node of [document.documentElement,document.body])if(node)themeObserver.observe(node,{attributes:true,attributeFilter:['class','style','data-theme']});
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
