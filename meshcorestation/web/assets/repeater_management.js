/* Remote repeater management. Session tokens stay in this page; login passwords are saved only by opt-in. */
(() => {
    let loginDialog, dialog, commandDialog, contact, session = '', admin = false, busy = false, schema = {}, selectedTab = 'status';
    const values = new Map(), inputs = new Map(), loaded = new Set();
    const $ = id => document.getElementById(id);
    const passwordKey = () => 'meshcorestation.repeater.password.' + contact.public_key.toLowerCase();
    function savedPassword() {
        try { return localStorage.getItem(passwordKey()) || ''; } catch { return ''; }
    }
    function savePassword(password) {
        try {
            if (password) localStorage.setItem(passwordKey(), password);
            else localStorage.removeItem(passwordKey());
            return true;
        } catch { return false; }
    }
    function node(tag, text, cls) { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; if (cls) item.className = cls; return item; }
    function button(text, handler, cls) { const item = node('button', text, cls); item.type = 'button'; item.addEventListener('click', handler); return item; }
    function message(text, error = false) { const box = $('repeater-message'); box.textContent = text; box.classList.toggle('repeater-error', error); }
    function controls() {
        for (const root of [dialog, loginDialog]) if (root) {
            root.setAttribute('aria-busy', String(busy));
            root.querySelectorAll('button,input,select,textarea').forEach(item => { item.disabled = busy || item.dataset.unavailable === 'true' || ((item.closest('#repeater-config') || item.closest('#repeater-console-form')) && (!admin || !session)); });
        }
        inputs.forEach((input, field) => { input.disabled = busy || !admin || !session || (schema[field].kind !== 'password' && !values.has(field)); });
        if ($('repeater-choose-map')) $('repeater-choose-map').disabled = !canPickLocation();
    }
    async function request(payload) {
        const response = await fetch('/api/repeater', {method: 'POST', cache: 'no-store', headers: {'Content-Type': 'application/json', 'X-Meshcore-Control': '1'}, body: JSON.stringify({...payload, public_key: contact.public_key, session})});
        let result;
        try { result = await response.json(); } catch { throw new Error('Unreadable response. A submitted change may have applied; read before retrying.'); }
        if (result.expired) { session = ''; admin = false; $('repeater-reconnect').hidden = false; }
        if (!response.ok || !result.ok) throw new Error(result.error || 'Repeater request failed.');
        if (typeof result.admin === 'boolean') admin = result.admin;
        return result;
    }
    async function run(work, report = message) {
        if (busy) return;
        busy = true; controls();
        try { await work(); } catch (error) { report(error.message, true); }
        finally { busy = false; controls(); }
    }
    function dirty() { return [...inputs].some(([field, input]) => schema[field].kind === 'password' ? input.value !== '' : values.has(field) && input.value !== values.get(field)); }
    function forget() {
        if (session) {
            // Retire the server token on close; no remote logout that would disturb monitoring.
            fetch('/api/repeater', {method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json', 'X-Meshcore-Control': '1'}, body: JSON.stringify({action: 'logout', public_key: contact.public_key, session})}).catch(() => {});
        }
        $('repeater-console-log').textContent='';$('repeater-console-command').value='';
        const frame = $('repeater-advisor-frame'); if (frame && !$('optimization-analysis-inline')) frame.removeAttribute('src');
        session = ''; inputs.forEach(input => { if (input.type === 'password') input.value = ''; });
    }
    function close() {
        if (busy || (dirty() && !window.confirm('Discard unsaved repeater edits?'))) return;
        forget(); dialog.close();
    }
    window.addEventListener('meshcorestation-optimizer-state',()=>{
        const frame=$('repeater-advisor-frame');
        if(frame?.contentWindow && (!$('optimization-analysis-inline') || ($('optimization-analysis-disclosure')?.open && $('repeater-optimizer-disclosure')?.open)))frame.contentWindow.postMessage({type:'meshcorestation-optimizer-refresh'},window.location.origin);
    });
    function tab(name) {
        if (name === 'advisor') {
            if (!admin || !session) { message('Connect as administrator to use Repeater Optimizer.', true); return; }
            const frame = $('repeater-advisor-frame');
            if (!frame.hasAttribute('src')) frame.src = '/repeater-optimizer';
            else if (selectedTab !== 'advisor') {
                // The Status tab can save fresh neighbor data while the
                // embedded optimizer stays loaded. Refresh locally on return.
                // A refresh does NOT send a LoRa request.
                frame.contentWindow.postMessage({type:'meshcorestation-optimizer-refresh'},window.location.origin);
            }
        }
        selectedTab = name;
        for (const value of ['status', 'config', 'console', 'advisor']) {
            const active = value === name;
            $('repeater-tab-' + value).setAttribute('aria-selected', String(active));
            $('repeater-tab-' + value).tabIndex = active ? 0 : -1;
            $('repeater-' + value).hidden = !active;
        }
    }
    function create() {
        dialog = node('dialog'); dialog.id = 'repeater-manage-dialog'; dialog.setAttribute('aria-labelledby', 'repeater-title');
        dialog.innerHTML = `<div class="dialog-header"><h2 id="repeater-title">Repeater management</h2><button type="button" id="repeater-close" aria-label="Close repeater management">×</button></div>
            <div class="repeater-fixed"><strong id="repeater-name"></strong><p id="repeater-identity" class="muted"></p><div class="repeater-tabs" role="tablist" aria-label="Repeater management">
            <button type="button" id="repeater-tab-status" role="tab" aria-controls="repeater-status">Status</button><button type="button" id="repeater-tab-config" role="tab" aria-controls="repeater-config">Configurations</button><button type="button" id="repeater-tab-console" role="tab" aria-controls="repeater-console">Console</button><button type="button" id="repeater-tab-advisor" role="tab" aria-controls="repeater-advisor" hidden>Repeater Optimizer</button></div></div>
            <div class="dialog-body"><p id="repeater-message" role="status" aria-live="polite"></p><button type="button" id="repeater-reconnect" hidden>Connect again</button>
            <section id="repeater-status" role="tabpanel" aria-labelledby="repeater-tab-status"><div class="repeater-toolbar"><span id="repeater-last-response" class="muted">Not yet read</span><button type="button" id="repeater-refresh">↻ Refresh</button></div><div id="repeater-status-cards"></div><div id="repeater-extras"></div></section>
            <section id="repeater-config" role="tabpanel" aria-labelledby="repeater-tab-config" hidden></section>
            <section id="repeater-console" role="tabpanel" aria-labelledby="repeater-tab-console" hidden><p class="muted">Send remote CLI commands as administrator. Commands run immediately and are not retried. Available commands depend on repeater firmware; serial-only commands cannot run over radio.</p><pre id="repeater-console-log" class="repeater-data" role="log" aria-label="Repeater console output" aria-live="polite"></pre><form id="repeater-console-form"><label for="repeater-console-command">Command</label><div class="repeater-toolbar"><input id="repeater-console-command" placeholder="e.g. get name" autocomplete="off" spellcheck="false" maxlength="147" required><button type="button" id="repeater-console-commands">Commands…</button><button type="submit">Send</button></div></form><button type="button" id="repeater-console-clear">Clear console</button><p class="muted">History is kept only while this management window is open. Password and private-key command text and replies are hidden. After using the console, read configuration values again before saving.</p></section><section id="repeater-advisor" role="tabpanel" aria-labelledby="repeater-tab-advisor" hidden><iframe id="repeater-advisor-frame" title="Repeater Optimizer" loading="lazy" referrerpolicy="same-origin"></iframe></section></div>`;
        document.body.append(dialog);
        const inline=$('optimization-analysis-inline');
        if(inline){
            const existing=inline.querySelector('iframe');
            const generated=dialog.querySelector('#repeater-advisor-frame');
            if(existing){generated.remove();}else{generated.title='Optimization Analysis';inline.append(generated);}
            const back=button('Return to Optimization Analysis',()=>{
                if(busy||!admin||!session)return;
                if(contact.public_key!==window.meshcorestationSelectedRepeater){message('Select this repeater in Repeater Management before opening analysis.',true);return;}
                if(dirty()&&!window.confirm('Discard unsaved repeater edits?'))return;
                dialog.close();$('repeater-optimizer-disclosure').open=true;$('optimization-analysis-disclosure').open=true;
                $('repeater-advisor-frame').contentWindow.postMessage({type:'meshcorestation-optimizer-context',public_key:contact.public_key,name:contact.name},window.location.origin);
            });
            back.id='analysis-return';dialog.querySelector('.repeater-fixed').append(back);
        }
        $('repeater-close').addEventListener('click', close);
        dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
        $('repeater-refresh').addEventListener('click', () => run(readStatus));
        $('repeater-reconnect').addEventListener('click', () => { if (dirty() && !window.confirm('Discard unsaved edits and reconnect?')) return; forget(); dialog.close(); openLogin(); });
        for (const name of ['status', 'config', 'console', 'advisor']) $('repeater-tab-' + name).addEventListener('click', () => tab(name));
        dialog.querySelector('[role="tablist"]').addEventListener('keydown', event => {
            if (busy || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault(); const tabs=admin&&!$('optimization-analysis-inline')?['status','config','console','advisor']:['status','config','console'];
            tab(event.key==='Home'?tabs[0]:event.key==='End'?tabs.at(-1):tabs[(tabs.indexOf(selectedTab)+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length]);
            $('repeater-tab-' + selectedTab).focus();
        });
        $('repeater-console-commands').onclick = openCommandPicker;
        $('repeater-console-clear').onclick=()=>{$('repeater-console-log').textContent='';};
        $('repeater-console-form').onsubmit=event=>{
            event.preventDefault();if(busy || !admin || !session)return;
            const input=$('repeater-console-command'),command=input.value.trim();
            if(!command)return;
            if(/<[^>]+>/.test(command)){message('Replace the command placeholders before sending.',true);return;}
            if(dirty() && !window.confirm('Discard unsaved configuration edits before sending a console command?'))return;
            if(new TextEncoder().encode(command).length>147){message('Use at most 147 UTF-8 bytes.',true);return;}
            const secret=/^(password(?: |$)|(?:get|set) (?:guest\.password|bridge\.secret|prv\.key)(?: |$))/.test(command);
            if(!/^(get |ver$|board$|clock$|neighbors$|region$|sensor (list|get)\b|gps$|powersaving$)/.test(command) && !window.confirm('Send this command to '+contact.name+'? It may change repeater settings or interrupt connectivity.'))return;
            input.value='';
            run(async()=>{
                consoleLine('> '+(secret?'[sensitive command]':command));
                values.clear();loaded.clear();inputs.forEach(entry=>{entry.value='';const hint=$(entry.id+'-hint');if(hint)hint.textContent='Read again after console command.';});
                try{const result=await request({action:'console',command,confirm:true});consoleLine(result.reply);message('Console command finished. Read configuration sections again before editing.');}
                catch(error){consoleLine('Error: '+error.message);throw error;}
            });
        };
        loginDialog = node('dialog'); loginDialog.id = 'repeater-login-dialog'; loginDialog.setAttribute('aria-labelledby', 'repeater-login-title');
        loginDialog.innerHTML = `<div class="dialog-header"><h2 id="repeater-login-title">Connect to repeater</h2><button type="button" id="repeater-login-close" aria-label="Close repeater login">×</button></div><div class="dialog-body"><p id="repeater-login-name"></p><form id="repeater-login-form"><label for="repeater-password">Admin password</label><div class="repeater-password"><input id="repeater-password" type="password" autocomplete="off"><button type="button" id="repeater-show-password" aria-label="Show password">Show</button></div><label class="repeater-remember"><input id="repeater-remember-password" type="checkbox" aria-describedby="repeater-remember-help"> Remember password</label><p class="muted" id="repeater-remember-help">Leave blank to use existing permissions or guest access. Remembered passwords are stored in this browser on this device. Uncheck to forget.</p><p id="repeater-login-message" role="status" aria-live="polite"></p><button type="submit">Connect</button></form></div>`;
        document.body.append(loginDialog);
        const closeLogin = () => { if (!busy) { $('repeater-password').value = ''; loginDialog.close(); } };
        $('repeater-remember-password').addEventListener('change', () => {
            if (!$('repeater-remember-password').checked && !savePassword('')) {
                $('repeater-login-message').textContent = 'Could not remove the saved password. Clear this site’s browser data to forget it.';
            }
        });
        $('repeater-login-close').addEventListener('click', closeLogin);
        loginDialog.addEventListener('cancel', event => { event.preventDefault(); closeLogin(); });
        $('repeater-show-password').addEventListener('click', () => { const input = $('repeater-password'), show = input.type === 'password'; input.type = show ? 'text' : 'password'; $('repeater-show-password').textContent = show ? 'Hide' : 'Show'; });
        $('repeater-login-form').addEventListener('submit', async event => {
            event.preventDefault(); if (busy) return;
            busy = true; controls(); $('repeater-login-message').textContent = 'Connecting… This can take up to 40 seconds.';
            const password = $('repeater-password').value; $('repeater-password').value = '';
            try {
                const result = await request({action: 'login', password});
                const remembered = savePassword($('repeater-remember-password').checked ? password : '');
                session = result.session; admin = result.admin; schema = result.fields;
                values.clear(); inputs.clear(); loaded.clear(); buildConfig(); buildExtras();
                if(!$('optimization-analysis-inline'))$('repeater-advisor-frame').removeAttribute('src');
                $('repeater-name').replaceChildren(window.MeshcoreStationRepeaterNames?.element(contact.public_key)||node('span',contact.name||'(unnamed repeater)'));
                identity(result.contact); $('repeater-reconnect').hidden = true;
                $('repeater-status-cards').replaceChildren(); $('repeater-last-response').textContent = 'Not yet read';
                loginDialog.close(); tab('status'); dialog.showModal();
                await readStatus();
                if (!remembered) message('Connected, but browser storage is unavailable. The remember-password choice could not be saved.', true);
            } catch (error) {
                if (dialog.open) message(error.message, true); else $('repeater-login-message').textContent = error.message;
            } finally { busy = false; controls(); }
        });
    }
    function consoleCommands() {
        const commands = [
            ['ver', 'Show the repeater firmware version.'],
            ['board', 'Show the repeater board model.'],
            ['clock', 'Read the repeater clock.'],
            ['time <unix-seconds>', 'Set the repeater clock to a Unix timestamp.'],
            ['advert', 'Transmit an advertisement so nearby nodes can discover this repeater.'],
            ['neighbors', 'List neighboring nodes heard by the repeater.'],
            ['region', 'List the forwarding regions.'],
            ['region put <name> <parent>', 'Create a region or change its parent; use * for the root.'],
            ['region remove <name>', 'Remove a forwarding region.'],
            ['region allowf <name>', 'Allow flood forwarding in a region.'],
            ['region denyf <name>', 'Block flood forwarding in a region.'],
            ['region home <name>', 'Select the home region.'],
            ['region default <name>', 'Select the default outgoing scope.'],
            ['region save', 'Save region changes so they survive a restart.'],
            ['setperm <public-key> <permission>', 'Set companion access: 0 guest, 1 read-only, 2 read-write, 3 admin.'],
            ['sensor list', 'List sensors supported by this firmware.'],
            ['sensor get <name>', 'Read a sensor setting; names depend on the firmware.'],
            ['sensor set <name> <value>', 'Change a sensor setting supported by this firmware.'],
            ['get extra.sf', 'Read extra spreading factors on supported radios.'],
            ['set extra.sf <values>', 'Configure extra spreading factors on supported radios; use a comma-separated list.'],
            ['reboot', 'Restart the repeater. The management connection will end.'],
            ['powersaving', 'Show whether power saving is enabled.'],
            ['gps', 'Show GPS state and fix information on supported boards.'],
        ];
        for (const [field, spec] of Object.entries(schema)) {
            const label = spec.label;
            if (spec.kind !== 'password') {
                const read = spec.read || 'get ' + field;
                if (!commands.some(([command]) => command === read)) commands.push([read, 'Read ' + label + '.']);
            }
            const choices = spec.options ? ' Allowed values: ' + spec.options.join(', ') + '.' :
                spec.kind === 'number' ? ` Range: ${spec.low}–${spec.high}${spec.step ? ', step ' + spec.step : ''}.` : '';
            const argument = spec.kind === 'radio' ? '<frequency>,<bandwidth>,<sf>,<cr>' : '<value>';
            commands.push([(spec.write || 'set ' + field) + ' ' + argument, 'Change ' + label + '.' + choices]);
        }
        return commands;
    }
    function openCommandPicker() {
        if (busy || !admin || !session) return;
        if (!commandDialog) {
            commandDialog = node('dialog'); commandDialog.id = 'repeater-command-dialog';
            commandDialog.setAttribute('aria-labelledby', 'repeater-command-title');
            commandDialog.innerHTML = `<div class="dialog-header"><h2 id="repeater-command-title">Console commands</h2><button type="button" id="repeater-command-close" aria-label="Close command picker">×</button></div><div class="dialog-body"><p class="muted">Choose a command to insert it without sending. Replace values in &lt;angle brackets&gt; before pressing Send. Availability depends on repeater firmware and hardware.</p><label for="repeater-command-search">Find a command</label><input id="repeater-command-search" type="search" placeholder="Search commands or descriptions" autocomplete="off"><div id="repeater-command-list"></div></div>`;
            document.body.append(commandDialog);
            $('repeater-command-close').onclick = () => commandDialog.close();
        }
        const search = $('repeater-command-search'), list = $('repeater-command-list');
        const render = () => {
            list.replaceChildren();
            const query = search.value.trim().toLowerCase();
            for (const [command, purpose] of consoleCommands()) {
                if (!(command + ' ' + purpose).toLowerCase().includes(query)) continue;
                const choice = button('', () => {
                    const input = $('repeater-console-command');
                    input.value = command;
                    commandDialog.close(); input.focus();
                    const placeholder = /<[^>]+>/.exec(command);
                    if (placeholder) input.setSelectionRange(placeholder.index, placeholder.index + placeholder[0].length);
                }, 'repeater-command-choice');
                choice.append(node('code', command), node('span', purpose)); list.append(choice);
            }
            if (!list.children.length) list.append(node('p', 'No matching commands.', 'muted'));
        };
        search.value = ''; search.oninput = render; render(); commandDialog.showModal(); search.focus();
    }
    function consoleLine(text) {
        const log=$('repeater-console-log');
        log.textContent=(log.textContent+window.meshcorestationFormatDate(new Date(),undefined,{timeOnly:true})+' '+text+'\n').slice(-24000);
        log.scrollTop=log.scrollHeight;
    }
    function identity(info) {
        const hops = info.out_path_len;
        $('repeater-identity').textContent = contact.public_key.slice(0, 12) + '… · ' + (hops === 0 ? 'Direct' : hops > 0 ? hops + ' hops' : 'Flood route') + (admin ? '' : ' · Guest access');
        $('repeater-identity').title = contact.public_key;
        const advisorTab = $('repeater-tab-advisor'); if (advisorTab) advisorTab.hidden = !admin || !!$('optimization-analysis-inline');
    }

    // Same-origin embedded advisor; credentials and radio session stay in management.
    const advisorFields = ['flood.max','flood.max.unscoped'];
    window.addEventListener('message', event => {
        const frame=$('repeater-advisor-frame');
        if(!frame || event.origin!==window.location.origin || event.source!==frame.contentWindow ||
            !['meshcorestation-advisor-request','meshcorestation-advisor-apply','meshcorestation-advisor-return',
              'meshcorestation-optimizer-neighbors','meshcorestation-optimizer-ready',
              'meshcorestation-optimizer-profile','meshcorestation-optimizer-storage',
              'meshcorestation-optimizer-clear-history'].includes(event.data?.type)) return;
        const inline=!!$('optimization-analysis-inline');
        const usable=()=>dialog?.open || (inline && $('optimization-analysis-disclosure')?.open && $('repeater-optimizer-disclosure')?.open);
        if(event.data.type==='meshcorestation-optimizer-ready'&&inline)return;
        if(event.data.type==='meshcorestation-optimizer-ready'){
            if(dialog.open && admin && session)
                frame.contentWindow.postMessage({type:'meshcorestation-optimizer-context',public_key:contact.public_key,name:contact.name},window.location.origin);
            return;
        }
        if(event.data.type==='meshcorestation-advisor-return'){
            if(dialog?.open){tab('config');$('repeater-tab-config').focus();}
            return;
        }
        const target=frame.contentWindow,payload=event.data;
        const send=data=>{if(usable()&&frame.contentWindow===target)target.postMessage({type:'meshcorestation-advisor-values',request_id:payload.request_id,...data},window.location.origin);};
        if(inline && (payload.public_key!==window.meshcorestationSelectedRepeater || payload.public_key!==contact?.public_key)){send({error:'Connect as administrator for the selected repeater, then return to Optimization Analysis.'});return;}
        if (busy || !session || !admin) { send({error:'Connect as administrator and finish any pending repeater operation.'}); return; }
        const progress=text=>{if(usable()&&frame.contentWindow===target)target.postMessage({type:'meshcorestation-advisor-progress',request_id:payload.request_id,text},window.location.origin);};
        progress('Management connected. Checking administrator session…');
        const options=['meshcorestation-optimizer-profile','meshcorestation-optimizer-storage','meshcorestation-optimizer-clear-history'].includes(payload.type);
        if(options){
            if(payload.public_key!==contact.public_key){send({error:'Selected repeater changed. Reopen Optimizer.'});return;}
            run(async()=>{
                try {
                    const body={action:payload.type==='meshcorestation-optimizer-profile'?'profile':
                        payload.type==='meshcorestation-optimizer-storage'?'storage':'clear_history',
                        public_key:contact.public_key,session};
                    if(body.action==='profile'){
                        body.role=payload.role;body.polling=payload.polling;
                    }else if(body.action==='storage') body.settings=payload.settings;
                    else if(body.action==='clear_history') body.confirm=payload.confirm===true;
                    const res=await fetch('/api/repeater-optimizer',{method:'POST',cache:'no-store',
                        headers:{'Content-Type':'application/json','X-Meshcore-Control':'1'},body:JSON.stringify(body)});
                    const data=await res.json();
                    if(!res.ok||!data.ok)throw Error(data.error||'Saving optimizer settings failed.');
                    send({saved:true,profile:data.profile,settings:data.settings,removed:data.removed});
                }catch(error){send({error:error.message});}
            });
            return;
        }
        const neighbors=payload.type==='meshcorestation-optimizer-neighbors';
        if(neighbors) {
            run(async()=>{
                try {
                    progress('Reading one neighbor page over LoRa…');
                    const data=await request({action:'neighbors',offset:0,optimizer:true});
                    send({public_key:contact.public_key,neighbors:data.data,
                        snapshot:data.neighbor_snapshot,neighbor_read:true});
                    message('Neighbor snapshot received and stored.');
                }catch(error){send({error:error.message});message(error.message,true);}
            });
            return;
        }
        const apply=payload.type==='meshcorestation-advisor-apply';
        if(apply && (payload.public_key!==contact.public_key || dirty())) {
            send({error:'Repeater changed or configuration edits are unsaved. Save or discard edits, then read again.'});return;
        }
        const changes=payload.changes;
        if(apply && (!Array.isArray(changes) || !changes.length || changes.length>advisorFields.length ||
            changes.some(item=>!item || !advisorFields.includes(item.field) || typeof item.expected!=='string' || typeof item.value!=='string') ||
            new Set(changes.map(item=>item.field)).size!==changes.length)) {send({error:'Invalid change list.'});return;}
        if(apply && !window.confirm('Apply to '+contact.name+' ('+contact.public_key.slice(0,12)+')?\n\n'+
            changes.map(item=>item.field+': '+item.expected+' → '+item.value).join('\n')+'\n\nChanges can affect mesh connectivity. Stop on the first unconfirmed result.')) {send({error:'Changes cancelled.'});return;}
        run(async()=>{
            const current={}, errors={}, results=[];
            try {
                if(apply) {
                    // Preflight every selected field before any write; write rechecks it again.
                    for(const item of changes) {
                        progress('Checking current '+item.field+' before changes…');
                        const read=await request({action:'read',field:item.field,optimizer:true});
                        if(String(read.value)!==item.expected)throw Error(item.field+' changed on the repeater. Read and review again.');
                    }
                    for(const item of changes) {
                        progress('Applying and verifying '+item.field+'…');
                        values.delete(item.field);
                        try {
                            const result=await request({action:'advisor_write',field:item.field,value:item.value,expected:item.expected,confirm:true});
                            current[item.field]=result.value;results.push({field:item.field,value:result.value});
                            if(String(result.value)!==item.value)throw Error('Readback differs for '+item.field+'. Remaining changes stopped.');
                        } catch(error) {errors[item.field]=error.message;break;}
                    }
                } else {
                    for(const field of advisorFields) {
                        progress('Reading '+field+' ('+(advisorFields.indexOf(field)+1)+'/'+advisorFields.length+')… Waiting for repeater reply.');
                        try {current[field]=(await request({action:'read',field,optimizer:true})).value;
                            if(usable()&&frame.contentWindow===target)target.postMessage({type:'meshcorestation-advisor-progress',request_id:payload.request_id,text:'Received '+field+'.',field,value:current[field]},window.location.origin);}
                        catch(error) {errors[field]=error.message;if(!session || /timed out|two minutes|Administrator/i.test(error.message))break;}
                    }
                }
                send({public_key:contact.public_key,name:contact.name,current,errors,results,applied:apply});
                message(apply?'Advisor operation finished. Read affected configuration sections again.':'Advisor read finished; form edits preserved.');
            } catch(error) {send({error:error.message,public_key:contact.public_key,results,applied:apply});}
        });
    });
    function openLogin() {
        $('repeater-login-name').replaceChildren(window.MeshcoreStationRepeaterNames?.element(contact.public_key)||node('span',contact.name||contact.public_key));
        $('repeater-login-message').textContent = ''; $('repeater-password').value = savedPassword();
        $('repeater-remember-password').checked = $('repeater-password').value !== ''; $('repeater-password').type = 'password'; $('repeater-show-password').textContent = 'Show';
        controls(); loginDialog.showModal(); $('repeater-password').focus();
    }
    document.addEventListener('analysis-connect',event=>window.meshcorestationManageRepeater(event.detail));
    document.addEventListener('analysis-disconnect',()=>{if(dialog&&!busy)forget();});
    document.addEventListener('managed-repeater-selected',()=>{
        if(dialog&&contact?.public_key!==window.meshcorestationSelectedRepeater){forget();if(dialog.open)dialog.close();if(loginDialog.open)loginDialog.close();}
    });
    window.meshcorestationManageRepeater = selected => {
        if (busy || selected.type !== 2) return;
        if (!dialog) create();
        if (dialog.open || loginDialog.open) return;
        if(session)forget();
        window.MeshcoreStationRepeaterNames?.ingest([selected]);
        contact = {...selected}; session = ''; admin = false; openLogin();
    };
    const duration = value => { if (!Number.isFinite(value)) return 'Not available'; const seconds = Math.max(0, Math.floor(value)); return `${Math.floor(seconds / 86400)}d ${Math.floor(seconds / 3600) % 24}h ${Math.floor(seconds / 60) % 60}m`; };
    const unit = (value, suffix = '') => Number.isFinite(value) ? value + suffix : 'Not available';
    function card(title, rows) {
        const section = node('section', undefined, 'repeater-section'), list = node('dl'); section.append(node('h3', title));
        for (const [label, value] of rows) list.append(node('dt', label), node('dd', value));
        section.append(list); return section;
    }
    async function readStatus() {
        message('Reading repeater status…');
        const result = await request({action: 'status'}), data = result.data, cards = $('repeater-status-cards');
        identity(result.contact);
        const clock = Number.isInteger(result.repeater_time) && result.repeater_time >= 0
            ? window.meshcorestationFormatDate(result.repeater_time,'Europe/Berlin') + ' · Europe/Berlin (' + window.meshcorestationFormatDate(result.repeater_time,'UTC')+' UTC' + ')'
            : 'Not reported by repeater firmware';
        cards.replaceChildren(card('System', [['Repeater clock (last read)', clock], ['Battery', Number.isFinite(data.bat) ? window.MeshcoreStationBattery.reading(data.bat / 1000) : 'Not available'], ['Uptime', duration(data.uptime)], ['Queue', unit(data.tx_queue_len)], ['Firmware level', unit(result.firmware_level)], ['Debug events', unit(data.full_evts)]]),
            card('Radio', [['Last RSSI', unit(data.last_rssi, ' dBm')], ['Last SNR', unit(data.last_snr, ' dB')], ['Noise floor', unit(data.noise_floor, ' dBm')], ['TX airtime', duration(data.airtime)], ['RX airtime', duration(data.rx_airtime)], ['Receive errors', unit(data.recv_errors)]]));
        const packet = node('section', undefined, 'repeater-section'); packet.append(node('h3', 'Packets'));
        packet.append(table(['Type', 'Sent', 'Received'], [['Flood', unit(data.sent_flood), unit(data.recv_flood)], ['Direct', unit(data.sent_direct), unit(data.recv_direct)], ['Total', unit(data.nb_sent), unit(data.nb_recv)]]));
        packet.append(node('p', 'Duplicates · Flood: ' + unit(data.flood_dups) + ' · Direct: ' + unit(data.direct_dups), 'muted')); cards.append(packet);
        $('repeater-last-response').textContent = 'Last response: ' + window.meshcorestationFormatDate(result.sampled_at,'Europe/Berlin') + ' · Europe/Berlin';
        message(admin ? 'Status received.' : 'Guest session: status is available; configurations require administrator access.');
    }
    function table(headings, rows) {
        const grid = node('table'), head = node('thead'), tr = node('tr'), body = node('tbody');
        headings.forEach(label => tr.append(node('th', label))); head.append(tr);
        rows.forEach(row => { const line = node('tr'); row.forEach(value => {const cell=node('td');if(value instanceof Node)cell.append(value);else cell.textContent=typeof value==='object'?JSON.stringify(value):String(value??'Not available');line.append(cell);}); body.append(line); });
        grid.append(head, body); return grid;
    }
    function disclosure(title, subtitle) {
        const details = node('details', undefined, 'repeater-section'), summary = node('summary'); summary.append(node('strong', title));
        if (subtitle) summary.append(node('small', subtitle, 'muted')); details.append(summary); return details;
    }
    function buildExtras() {
        const root = $('repeater-extras'); root.replaceChildren();
        for (const [action, label] of [['telemetry', 'Telemetry'], ['neighbors', 'Neighbors']]) {
            const box = disclosure(label), content = node('div', undefined, 'repeater-extra-content');
            const localMessage = node('p', '', 'muted');
            localMessage.setAttribute('role', 'status'); localMessage.setAttribute('aria-live', 'polite');
            if (action === 'neighbors') localMessage.id = 'repeater-neighbors-message';
            const report = action === 'neighbors' ? (text, error = false) => { localMessage.textContent = text; localMessage.classList.toggle('repeater-error', error); } : message;
            let offset = 0;
            const load = async (more = false) => {
                report('Reading ' + label.toLowerCase() + '…');
                const result = await request({action, offset: more ? offset : 0});
                if (!more) content.replaceChildren();
                if (action === 'neighbors') {
                    const data = result.data, rows = data.neighbours || [];
                    window.MeshcoreStationRepeaterNames?.ingest(rows,'cached');
                    content.append(table(['Repeater', 'Last heard', 'SNR'], rows.map(row => [window.MeshcoreStationRepeaterNames?.element(row.pubkey)||row.name||row.pubkey, duration(row.secs_ago) + ' ago', unit(row.snr, ' dB')])));
                    offset = (more ? offset : 0) + rows.length;
                    next.hidden = offset >= data.neighbours_count || rows.length === 0;
                    content.append(node('p', `${offset} / ${data.neighbours_count} neighbors`, 'muted'));
                } else {
                    if (Array.isArray(result.data)) content.append(result.data.length ? table(['Channel', 'Sensor', 'Value'], result.data.map(row => [row.channel, row.type, Number.isFinite(row.value) && row.type === 'voltage' ? row.value.toFixed(2) + ' V' : Number.isFinite(row.value) && row.type === 'temperature' ? row.value.toFixed(1) + ' °C' : row.value])) : node('p', 'The repeater returned no sensor readings.'));
                    else content.append(node('pre', JSON.stringify(result.data, null, 2), 'repeater-data'));
                }
                loaded.add(action);
                if (action === 'neighbors') {
                    const snap = result.neighbor_snapshot;
                    report(snap
                        ? label + ' received. Snapshot #' + snap.id + ': ' +
                          snap.neighbors + ' of ' + snap.received +
                          ' returned entries saved (' +
                          (snap.reported==null?'total unknown':snap.reported+' reported total') + ').'
                        : 'Neighbor response received, but no saved snapshot confirmation was returned.',
                        !snap);
                } else report(label + ' received.');
            };
            const refresh = button('↻ Refresh', () => run(() => load(), report)), next = button('Load more', () => run(() => load(true), report)); next.hidden = true;
            box.append(refresh); if (action === 'neighbors') box.append(localMessage); box.append(content); if (action === 'neighbors') box.append(next);
            box.addEventListener('toggle', () => { if (box.open && !loaded.has(action) && !busy) run(() => load(), report); }); root.append(box);
        }
    }
    function fieldValue(field) {
        const input = inputs.get(field);
        if (schema[field].kind === 'radio') return [...input.querySelectorAll('input')].map(item => item.value).join(',');
        return input.value;
    }
    function setValue(field, value) {
        const input = inputs.get(field); values.set(field, value);
        if (schema[field].kind === 'radio') {
            const parts = value.split(','); input.querySelectorAll('input').forEach((item, i) => { item.value = parts[i] || ''; });
        } else input.value = schema[field].kind === 'textarea' ? value.replaceAll('|', '\n') : value;
        // Keep comparisons in the same representation the user edits.
        values.set(field, fieldValue(field));
    }
    function makeField(field, spec) {
        const label = node(spec.kind === 'radio' ? 'div' : 'label', spec.label, 'repeater-field'); let input;
        if (spec.kind === 'radio') {
            input = node('fieldset', undefined, 'repeater-radio-fields'); input.append(node('legend', 'Radio parameters'));
            for (const [name, placeholder] of [['Frequency (MHz)', '868.000'], ['Bandwidth (kHz)', '62.5'], ['Spreading factor', '7'], ['Coding rate', '5']]) {
                const part = node('label', name), entry = node('input'); entry.type = 'number'; entry.step = 'any'; entry.placeholder = placeholder; entry.setAttribute('aria-label', name); part.append(entry); input.append(part);
            }
            // A value property lets shared dirty-state handling treat this group as one field.
            Object.defineProperty(input, 'value', {get: () => [...input.querySelectorAll('input')].map(i => i.value).join(',')});
        } else if (spec.kind === 'select') {
            input = node('select'); spec.options.forEach((value, i) => { const option = node('option', spec.labels?.[i] || value); option.value = value; input.append(option); });
        } else {
            input = node(spec.kind === 'textarea' ? 'textarea' : 'input');
            if (input.tagName === 'INPUT') input.type = spec.kind === 'password' ? 'password' : spec.kind === 'number' ? 'number' : 'text';
            if (spec.kind === 'number') { input.min = spec.low; input.max = spec.high; input.step = spec.step || 'any'; }
            if (spec.kind === 'password') { input.autocomplete = 'new-password'; input.placeholder = 'Leave blank to keep unchanged'; }
        }
        input.id = 'repeater-field-' + field.replaceAll('.', '-'); input.setAttribute('aria-label', spec.label); inputs.set(field, input);
        label.append(input); const hint = node('small', spec.kind === 'password' ? 'Write-only; not saved in MeshcoreStation.' : 'Read this section to load the current value.', 'muted'); hint.id = input.id + '-hint'; label.append(hint);
        return label;
    }
    const sections = [['basic', 'Basic settings', ''], ['radio', 'Radio', 'Frequency, bandwidth, SF, CR, TX power'], ['location', 'Location', 'Latitude and longitude'], ['advertisements', 'Advertisements', 'Local and flood intervals'], ['routing', 'Routing and regions', 'Forwarding, hop limits and regions'], ['access', 'Access', 'Guest access and permissions'], ['owner', 'Owner information', ''], ['advanced', 'Advanced', ''], ['gps', 'GPS', 'Requires GPS support'], ['bridge', 'Bridge', 'Requires a bridge-enabled firmware build']];
    function canPickLocation() { return !busy && admin && !!session && values.has('lat') && values.has('lon'); }
    function buildConfig() {
        const root = $('repeater-config'); root.replaceChildren();
        for (const [section, title, subtitle] of sections) {
            const box = disclosure(title, subtitle); box.open = section === 'basic';
            const form = node('form'), fields = Object.keys(schema).filter(field => schema[field].section === section), grid = node('div', undefined, 'repeater-fields');
            fields.forEach(field => grid.append(makeField(field, schema[field]))); form.append(grid);
            const toolbar = node('div', undefined, 'repeater-toolbar');
            toolbar.append(button('Read', () => run(() => readSection(fields)))); const save = node('button', 'Save section'); save.type = 'submit'; toolbar.append(save); form.append(toolbar);
            form.addEventListener('submit', event => { event.preventDefault(); if (form.reportValidity()) run(() => saveSection(fields)); });
            box.append(form);
            if (section === 'location') {
                const choose = button('Choose on map', () => {
                    if (!canPickLocation()) return;
                    window.MeshcoreStationRepeaterLocation.open({current: [values.get('lat'), values.get('lon')], draft: [inputs.get('lat').value, inputs.get('lon').value], canEdit: canPickLocation,
                        report: message, apply: point => { inputs.get('lat').value = point[0].toFixed(6); inputs.get('lon').value = point[1].toFixed(6); message('Position applied to the fields. Click Save section to update the repeater.'); }});
                });
                choose.id = 'repeater-choose-map'; form.insertBefore(choose, grid);
            }
            if (section === 'routing') buildRegions(box);
            if (section === 'access') buildPermissions(box);
            root.append(box);
        }
        const actions = node('section', undefined, 'repeater-section'); actions.append(node('h3', 'Actions'));
        const toolbar = node('div', undefined, 'repeater-action-buttons');
        for (const [name, title] of [['advert', 'Send advert'], ['clock_sync', 'Sync clock'], ['reboot', 'Reboot repeater']]) toolbar.append(button(title, () => {
            if (!window.confirm(`${title} on ${contact.name}?`)) return;
            run(async () => { message(title + '…'); const result = await request({action: 'action', name, confirm: true}); message(result.message); });
        }, name === 'reboot' ? 'repeater-danger' : ''));
        actions.append(toolbar); root.append(actions, node('p', 'Available settings depend on firmware. Read values before editing. Sections are saved separately.', 'muted'));
    }
    async function readSection(fields) {
        if (fields.some(field => schema[field].kind !== 'password' && values.has(field) && fieldValue(field) !== values.get(field)) && !window.confirm('Discard unsaved edits in this section and read current values?')) return;
        const failures = [];
        for (const field of fields) {
            if (schema[field].kind === 'password') continue;
            message('Reading ' + schema[field].label + '…');
            try {
                const result = await request({action: 'read', field}); setValue(field, result.value);
                $(inputs.get(field).id + '-hint').textContent = 'Read from repeater.';
            } catch (error) { values.delete(field); $(inputs.get(field).id + '-hint').textContent = error.message; failures.push(schema[field].label + ': ' + error.message); if (!session || /timed out|timeout|two minutes|Administrator/i.test(error.message)) break; }
        }
        message(failures.length ? failures.join('\n') : 'Section read from repeater.', failures.length > 0);
    }
    async function saveSection(fields) {
        const changed = fields.filter(field => schema[field].kind === 'password' ? fieldValue(field) !== '' : values.has(field) && fieldValue(field) !== values.get(field));
        if (!changed.length) { message('No changes to save.'); return; }
        const review = changed.map(field => schema[field].label + ': ' + (schema[field].kind === 'password' ? '(new password)' : fieldValue(field))).join('\n');
        if (!window.confirm(`Save to ${contact.name}?\n\n${review}${changed.includes('radio') ? '\n\nRadio changes may require a reboot and can affect connectivity.' : ''}`)) return;
        const saved = []; let reboot = false;
        for (const field of changed) {
            message('Saving ' + schema[field].label + '…');
            const value = fieldValue(field), expected = values.get(field);
            // Do not keep a submitted password in the form, including on failure.
            if (schema[field].kind === 'password') inputs.get(field).value = '';
            try {
                const result = await request({action: 'write', field, value, expected: schema[field].kind === 'textarea' ? expected?.replaceAll('\n', '|') : expected, confirm: true});
                if (schema[field].kind !== 'password') setValue(field, result.value);
                saved.push(schema[field].label); reboot ||= result.reboot_required;
                $(inputs.get(field).id + '-hint').textContent = result.message;
            } catch (error) {
                if (schema[field].kind !== 'password') values.delete(field);
                message(`${saved.length ? 'Confirmed: ' + saved.join(', ') + '. ' : ''}${schema[field].label}: ${error.message} Remaining fields were not sent. Read this section before retrying.`, true); return;
            }
        }
        message('Confirmed: ' + saved.join(', ') + '.' + (reboot ? ' Reboot required to apply radio settings.' : ''));
    }
    function buildRegions(box) {
        const section = node('div', undefined, 'repeater-subsection'), output = node('pre', 'Regions have not been read.', 'repeater-data');
        section.append(node('h4', 'Regions'), button('Read regions', () => run(async () => { const result = await request({action: 'regions_read'}); output.textContent = result.data; message('Region response received.'); })), output);
        const form = node('form'), name = node('input'), parent = node('input'), operation = node('select');
        name.placeholder = 'Region name, e.g. #Europe'; name.required = true; name.setAttribute('aria-label', 'Region name'); parent.placeholder = 'Parent region (default *)'; parent.setAttribute('aria-label', 'Parent region');
        for (const [value, label] of [['put', 'Add / update parent'], ['remove', 'Remove'], ['allowf', 'Allow flooding'], ['denyf', 'Block flooding'], ['home', 'Set home'], ['default', 'Set default scope']]) { const option = node('option', label); option.value = value; operation.append(option); }
        operation.setAttribute('aria-label', 'Region operation'); form.append(name, parent, operation); const apply = node('button', 'Apply region change'); apply.type = 'submit'; form.append(apply);
        form.addEventListener('submit', event => { event.preventDefault(); if (!form.reportValidity() || !window.confirm(`${operation.selectedOptions[0].textContent}: ${name.value} on ${contact.name}?`)) return; run(async () => { const result = await request({action: 'region', verb: operation.value, name: name.value, parent: parent.value, confirm: true}); message(result.message); }); });
        section.append(form, node('p', 'These are the repeater’s forwarding regions. Names, including any # prefix, are sent exactly as entered. Long region lists may be truncated by firmware.', 'muted')); box.append(section);
    }
    function buildPermissions(box) {
        const section = node('div', undefined, 'repeater-subsection'), output = node('div'); section.append(node('h4', 'Companion permissions'));
        section.append(button('Read permissions', () => run(async () => { const result = await request({action: 'acl'}); output.replaceChildren(table(['Public key prefix', 'Permission'], result.data.map(row => [row.key, row.perm]))); message('Permissions received.'); })), output);
        const form = node('form'), key = node('input'), permission = node('select'); key.placeholder = 'Full companion public key'; key.pattern = '[a-fA-F0-9]{64}'; key.required = true; key.setAttribute('aria-label', 'Companion public key');
        ['Guest (0)', 'Read-only (1)', 'Read-write (2)', 'Admin (3)'].forEach((text, i) => { const option = node('option', text); option.value = String(i); permission.append(option); }); permission.setAttribute('aria-label', 'Permission');
        const save = node('button', 'Apply permission'); save.type = 'submit'; form.append(key, permission, save);
        form.addEventListener('submit', event => { event.preventDefault(); if (!form.reportValidity() || !window.confirm(`Set ${permission.selectedOptions[0].textContent} for ${key.value}? Changing your companion’s permission may end management access.`)) return; run(async () => { const result = await request({action: 'permission', target: key.value, permission: permission.value, confirm: true}); message(result.message); }); });
        section.append(form); box.append(section);
    }
})();
