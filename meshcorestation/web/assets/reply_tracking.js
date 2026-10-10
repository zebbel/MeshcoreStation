/* Passive reply observations, refreshed only while command details are open. */
(() => {
    let current=null,sequence=0;
    const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
    function section(){
        let box=document.getElementById('reply-tracking');
        const fields=document.getElementById('detail-fields');
        if(!box&&fields){box=node('section');box.id='reply-tracking';box.className='commands-preview';fields.before(box);}
        return box;
    }
    async function refresh(){
        const dialog=document.getElementById('details-dialog');
        if(!dialog?.open||current===null)return;
        const id=++sequence,box=section();
        if(!box)return;
        try {
            const result=await fetch('/api/replies/'+current,{cache:'no-store',headers:{'X-Meshcore-Control':'1'},signal:AbortSignal.timeout(10000)});
            const data=await result.json();if(!result.ok)throw Error(data.error||'Reply tracking unavailable.');
            if(id!==sequence||!dialog.open)return;
            box.replaceChildren(node('h3','Outgoing replies'));
            box.append(node('p','Forwarding observed means a matching repeated packet contained that repeater in its path. No observation does not prove delivery failed. Receiver delivery is not confirmed.'));
            if(!data.replies.length)box.append(node('p','No tracking records for this command. Older commands and sends without matching identity/channel data cannot be tracked retrospectively.'));
            data.replies.forEach((reply,i)=>{
                const item=node('article'),title=node('h4','Reply '+(i+1));
                const labels={accepted:'Accepted by companion',rejected:'Rejected by companion',uncertain:'Send result uncertain',submitting:'Submission started; result not recorded yet'};
                item.append(title,node('p',(labels[reply.send_status]||reply.send_status)+' · '+reply.scope),node('pre',reply.message));
                if(reply.detail)item.append(node('p',reply.detail));
                if(!reply.observations.length){
                    const listening=Date.now()/1000<reply.created_at+data.window_seconds;
                    item.append(node('p',listening?'Forwarding not confirmed — listening for matching copies (up to 5 minutes).':'Forwarding not confirmed — no matching repeater copy recorded.'));
                }
                reply.observations.forEach(observation=>{
                    const route=observation.route.map(h=> (h.name||h.prefix)+' ['+h.prefix+'] · '+h.status).join(' → ');
                    item.append(node('p',new Date(observation.seen_at*1000).toLocaleString()+' · '+observation.latency.toFixed(1)+'s after submission'),
                        node('p',route),
                        node('small','Received at this station: RSSI '+(observation.rssi??'--')+' dBm · SNR '+(observation.snr??'--')+' dB'));
                });
                box.append(item);
            });
        }catch(e){if(id===sequence&&dialog.open){box.replaceChildren(node('h3','Outgoing replies'),node('p',e.message));}}
    }
    document.addEventListener('click',event=>{
        const button=event.target.closest('button[data-details]');
        if(button){
            current=JSON.parse(button.dataset.details).id;++sequence;
            const box=section();if(box)box.replaceChildren(node('p','Loading outgoing replies…'));
            setTimeout(refresh,0);
        }
    });
    setInterval(refresh,5000);
})();
