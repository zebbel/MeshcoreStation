/* One asynchronous installed-branch check per dashboard load. Never installs. */
(() => {
    let attached=false, result=null;
    const $=id=>document.getElementById(id);
    async function api(body){
        const response=await fetch('/api/update',{method:body?'POST':'GET',cache:'no-store',headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(body?130000:10000)});
        const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Update service unavailable.');return data;
    }
    async function check(){
        try{
            result=await api();
            $('footer-version').textContent=`MeshcoreStation ${result.version} · ${result.branch}`;
            if(!result.branch||result.branch==='unknown')throw Error('Installed branch unavailable.');
            const checked=await api({action:'check',branch:result.branch});
            if(checked.check?.branch!==result.branch)throw Error('Installed-branch update check unavailable.');
            result={...result,check:checked.check,ready:checked.check.ready};
            $('footer-update').textContent=checked.check.available?'New revision available':'Up to date';
            $('footer-update-button').hidden=!checked.check.available;
        }catch(error){$('footer-update').textContent='Update check unavailable';$('footer-update').title=error.message;}
    }
    async function firmware(){
        try{
            const response=await fetch('/api/companion/firmware',{cache:'no-store',headers:{'X-Meshcore-Control':'1'},signal:AbortSignal.timeout(10000)}),data=await response.json();
            if(!response.ok||!data.ok||!data.connected)throw Error('Companion not connected.');
            const parts=[data.device?.ver,data.device?.fw_build].filter(Boolean);
            $('footer-firmware').textContent=parts.length?'Companion firmware '+parts.join(' · '):'Companion firmware unavailable';
        }catch(_){$('footer-firmware').textContent='Companion firmware unavailable';}
    }
    function attach(){
        const footer=$('dashboard-footer');if(attached||!footer)return;attached=true;
        $('footer-copyright').textContent=`© ${new Date().getFullYear()} zebbel`;
        const resize=()=>document.documentElement.style.setProperty('--dashboard-footer-height',Math.ceil(footer.getBoundingClientRect().height)+'px');
        if(window.ResizeObserver)new ResizeObserver(resize).observe(footer);resize();
        $('footer-update-button').onclick=()=>{try{window.meshcorestationOpenInstalledUpdate(result);}catch(error){$('footer-update').textContent=error.message;}};
        check();firmware();
    }
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
})();
