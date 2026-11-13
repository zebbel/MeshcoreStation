/* Passive reply observations, refreshed only while command details are open. */
(() => {
    const {translatedError: uiError, t: ui} = window.MeshcoreStationI18n || {
        translatedError: value => value,
        t: (id, ...values) => id.replace(/\{(\d+)\}/g, (_, i) => String(values[i] ?? `{${i}}`))
    };
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
            const data=await result.json();if(!result.ok)throw Error(data.error||ui("Reply tracking unavailable."));
            if(id!==sequence||!dialog.open)return;
            box.replaceChildren(node('h3',ui("Outgoing replies")));
            box.append(node('p',ui("Forwarding observed means a matching repeated packet contained that repeater in its path. No observation does not prove delivery failed. Receiver delivery is not confirmed.")));
            if(!data.replies.length)box.append(node('p',ui("No tracking records for this command. Older commands and sends without matching identity/channel data cannot be tracked retrospectively.")));
            data.replies.forEach((reply,i)=>{
                const item=node('article'),title=node('h4',ui("Reply ")+(i+1));
                const labels={accepted:ui("Accepted by companion"),rejected:ui("Rejected by companion"),uncertain:ui("Send result uncertain"),queued:ui("Queued in room; recipient delivery unconfirmed"),submitting:ui("Submission started; result not recorded yet")};
                item.append(title,node('p',(reply.scope.startsWith('Room: ')?ui("Room reply · "):ui("Channel reply · "))+reply.scope),node('pre',reply.message));
                item.append(node('p',ui("Retry status: ")+(reply.retry_status?ui(reply.retry_status):ui("legacy record"))+(reply.retry_detail?' — '+reply.retry_detail:'')));
                if(reply.next_retry_at)item.append(node('p',ui("Next attempt no earlier than ")+window.meshcorestationFormatDate(reply.next_retry_at)));
                const maximum=reply.max_attempts;
                (reply.attempts||[reply]).forEach((reply,index)=>{
                    item.append(node('h5',ui("Attempt ")+(reply.attempt||index+1)+(maximum?' / '+maximum:'')),
                        node('p',labels[reply.send_status]||reply.send_status),
                        node('p',ui("Submitted ")+window.meshcorestationFormatDate(reply.created_at)+(Number.isInteger(reply.timestamp)?ui(" · Packet timestamp ")+reply.timestamp+' ('+window.meshcorestationFormatDate(reply.timestamp)+')':'')));

                    if(reply.detail)item.append(node('p',reply.detail));
                    if(reply.scope.startsWith('Room: ')){
                        item.append(node('p',ui("Room synchronization and per-session acknowledgments are separate from channel forwarding evidence. Recipient delivery is unconfirmed here.")));
                    } else if(!reply.observations.length){
                        const listening=Date.now()/1000<reply.created_at+data.window_seconds;
                        item.append(node('p',listening?ui("Forwarding not confirmed — listening for matching copies (up to 5 minutes)."):ui("Forwarding not confirmed — no matching repeater copy recorded.")));
                    }
                    reply.observations.forEach(observation=>{
                        const route=observation.route.map(h=> (h.name||h.prefix)+' ['+h.prefix+'] · '+ui(h.status)).join(' → ');
                        item.append(node('p',window.meshcorestationFormatDate(observation.seen_at)+' · '+observation.latency.toFixed(1)+ui("s after submission")),
                            node('p',route),
                            node('small',ui("Received at this station: RSSI ")+(observation.rssi??'--')+ui(" dBm · SNR ")+(observation.snr??'--')+' dB'));
                    });
                });
                box.append(item);
            });
        }catch(e){if(id===sequence&&dialog.open){box.replaceChildren(node('h3',ui("Outgoing replies")),node('p',e.message));}}
    }
    document.addEventListener('click',event=>{
        const button=event.target.closest('button[data-details]');
        if(button){
            current=JSON.parse(button.dataset.details).id;++sequence;
            const box=section();if(box)box.replaceChildren(node('p',ui("Loading outgoing replies…")));
            setTimeout(refresh,0);
        }
    });
    setInterval(refresh,5000);
})();
