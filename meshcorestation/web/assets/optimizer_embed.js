/* The analysis iframe measures its intrinsic content, never the viewport height. */
(() => {
    if(window.parent===window)return;
    document.body.dataset.embedded='true';
    const main=document.querySelector('main');
    let scheduled=false,last=0;
    function measure(){
        scheduled=false;
        const height=Math.ceil(main.getBoundingClientRect().height)+2;
        if(height>0&&height!==last){last=height;window.parent.postMessage({type:'meshcorestation-optimizer-height',height},location.origin);}
    }
    function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(measure);}}
    if(window.ResizeObserver)new ResizeObserver(schedule).observe(main);
    else new MutationObserver(schedule).observe(main,{subtree:true,childList:true,attributes:true,characterData:true});
    window.addEventListener('resize',schedule);
    document.addEventListener('toggle',schedule,true);
    document.fonts?.ready.then(schedule);
    window.addEventListener('message',event=>{
        if(event.origin!==location.origin||event.source!==window.parent||event.data?.type!=='meshcorestation-optimizer-theme')return;
        const palette=event.data.palette||{};
        for(const name of ['--bg','--panel','--text','--muted','--border','--accent','--soft','--green','--red','--shadow','--control-radius','--control-padding']){
            if(typeof palette[name]==='string'&&palette[name].length<200)document.documentElement.style.setProperty(name,palette[name]);
        }
        schedule();
    });
    schedule();
})();
