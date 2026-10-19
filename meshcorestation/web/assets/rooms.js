/* Independent room dashboard; never inserts message content as HTML. */
(() => {
  'use strict';
  if (location.pathname !== '/rooms') return;
  const $ = id => document.getElementById(id);
  let rooms = [], selected = null, busy = false;
  const embedded = new URLSearchParams(location.search).get('embedded') === '1';
  if (embedded) document.body.classList.add('rooms-embedded');
  let contacts = [], contactsBusy = false, membersKey = null, qrRoom = null, shownRoom = null;
  function current() { return rooms.find(r => r.id === selected); }
  async function request(body) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch('/api/rooms', {method:body?'POST':'GET', headers:{'X-Meshcore-Control':'1','Content-Type':'application/json'}, body:body?JSON.stringify(body):undefined,signal:controller.signal});
      const result = await response.json();
      if (!response.ok || !result.ok) throw Error(result.error || 'Room request failed');
      return result;
    } finally { clearTimeout(timer); }
  }
  function contactName(key) { return contacts.find(c=>c.public_key===key.toLowerCase())?.name?.trim() || ''; }
  function shortKey(key) { return key.slice(0,6)+'…'+key.slice(-4); }
  function updateRoomActions() {
    const room=current(), toggle=$('toggle'), deletion=$('delete-room');
    toggle.disabled = !room || busy || (!room.enabled && !room.auth_revision);
    $('bot-channel').disabled = !room || busy;
    deletion.disabled = !room || busy || !!room.enabled || !!room.is_bot;
    deletion.title = !room ? 'Select a room.' : room.is_bot
      ? 'Switch the bot to another channel before deleting.'
      : room.enabled ? 'Disable this room before deleting it.'
      : 'Permanently remove the room and its data.';
    $('room-action-hint').textContent = !room ? '' : room.is_bot
      ? 'This room is the bot channel. Switch to another channel before deleting it.'
      : room.enabled ? 'Disable this room before deleting it.'
      : !room.auth_revision ? 'Save a room password below to enable this room.'
      : '';
  }
  function renderMembers() {
    const room=current();
    const members=(room?.members || []).filter(m=>m.public_key!==room.public_key);
    const signature=JSON.stringify([selected,members,contacts]);
    if(signature===membersKey)return;
    membersKey=signature;
    $('members').replaceChildren(...members.map(m=>{
      const li=document.createElement('li'),identity=document.createElement('div'),name=document.createElement('strong'),note=document.createElement('small');
      const known=contactName(m.public_key), display=known || shortKey(m.public_key);
      identity.className='member-identity';name.textContent=display;name.title=m.public_key;
      note.textContent=known?'Known contact':'Unknown contact';identity.append(name,note);
      const permission=document.createElement('select');permission.className='member-permission';
      permission.setAttribute('aria-label','Permission for '+display);
      for(const [value,label] of [['reader','Read'],['writer','Write']]){const option=document.createElement('option');option.value=value;option.textContent=label;permission.append(option);}
      permission.value=m.role;
      permission.onchange=()=>{const role=permission.value;permission.value=m.role;change({action:'grant',key:m.public_key,role});};
      const remove=document.createElement('button');remove.textContent='Remove';remove.type='button';remove.className='member-remove';remove.setAttribute('aria-label','Remove '+display);remove.onclick=()=>change({action:'revoke',key:m.public_key});
      li.append(identity,permission,remove);return li;
    }));
    if(!members.length)$('members').textContent='No participants yet. Members appear after password login.';
  }
  function render(result, full) {
    rooms = result.rooms; lastStatus = result.status;
    if (!rooms.some(r => r.id === selected)) selected = rooms[0]?.id ?? null;
    $('status').textContent = (result.status.running ? 'Room worker ready' : 'Room worker stopped') + ` · ${result.status.sessions} connected members · ${result.status.queued_commands || 0} queued commands · ${result.status.dropped_commands || 0} dropped commands · ${result.status.dropped_packets} dropped input packets` + (result.status.error ? ' · '+result.status.error : '');
    if (full) {
      $('room').replaceChildren(...rooms.map(r => {const option = document.createElement('option');option.value=r.id;option.textContent=r.name+(r.enabled?' · enabled':' · disabled');return option;}));
      $('room').value = selected;
    }
    const room = current(); $('details').hidden = !room;
    if (shownRoom !== selected) {
      shownRoom=selected; qrRoom=null; $('room-qr').hidden=true; $('room-qr-image').removeAttribute('src');
      $('show-qr').textContent='Show room QR code'; $('room-password').value='';
    }
    if (!room) { updateRoomActions(); return; }
    $('title').textContent = room.name; $('state').textContent = room.enabled ? 'Enabled' : 'Disabled · no room radio traffic';
    $('toggle').textContent = room.enabled ? 'Disable room' : 'Enable room'; $('send').disabled = !room.enabled;
    $('bot-channel').textContent = room.is_bot ? 'Bot channel ✓' : 'Use as bot channel';

    $('public-key').value = room.public_key;
    $('password-state').textContent=room.auth_revision ? 'Password is set. Enter a new password only to change it.' : 'Set a password, then enable this room. Existing history and identity are preserved.';
    updateRoomActions();
    renderMembers();
    $('posts').replaceChildren(...room.posts.map(p => {
      const row=document.createElement('article'), label=document.createElement('small'), text=document.createElement('p');
      label.textContent=new Date(p.timestamp*1000).toLocaleString()+' · '+(p.author===room.public_key?'Room':contactName(p.author) || shortKey(p.author));label.title=p.author;text.textContent=p.text;row.append(label,text);return row;
    }));
    if (!room.posts.length) $('posts').textContent='No messages yet.';
  }
  async function change(body, clear) {
    if (busy) return;busy=true;$('error').textContent='';
    updateRoomActions();
    $('members').querySelectorAll('select,button').forEach(n=>n.disabled=true);
    try {render(await request({room:selected,...body}),true);if(clear)$(clear).value='';}
    catch(e){$('error').textContent=e.message;}
    finally {busy=false;updateRoomActions();$('members').querySelectorAll('select,button').forEach(n=>n.disabled=false);}
  }
  $('show-qr').onclick=async()=>{
    if (!$('room-qr').hidden) { $('room-qr').hidden=true; $('show-qr').textContent='Show room QR code'; return; }
    const rid=selected; if (!rid) return;
    $('show-qr').disabled=true;
    try {
      if (qrRoom!==rid) {
        const card=await request({action:'qr',room:rid});
        if (selected!==rid) return;
        $('room-qr-image').src=card.image; qrRoom=rid;
      }
      $('room-qr').hidden=false; $('show-qr').textContent='Hide room QR code';
    } catch(e) { $('error').textContent=e.message; }
    finally { $('show-qr').disabled=false; }
  };
  async function updateContacts(){
    if(contactsBusy)return;
    contactsBusy=true;$('update-contact').disabled=true;$('contact-status').textContent='Updating contact names…';
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),25000);
    try {
      const response=await fetch('/api/companion/contacts',{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal:controller.signal});
      const result=await response.json();
      if(!response.ok || !result.ok)throw Error(result.error || 'Could not update contacts');
      contacts=(result.contacts || []).filter(c=>Number(c.type)===1 && /^[0-9a-f]{64}$/i.test(c.public_key)).map(c=>({...c,public_key:c.public_key.toLowerCase()}));
      render({rooms,status:lastStatus},false);
      $('contact-status').textContent=contacts.length?'Contact names updated.':'No companion contacts found. Unknown members keep their shortened keys.';
    }catch(e){$('contact-status').textContent=(e.name==='AbortError'?'Contact update timed out.':e.message)+' Existing names are retained; press Update contact to retry.';}
    finally{clearTimeout(timeout);contactsBusy=false;$('update-contact').disabled=false;}
  }
  $('update-contact').onclick=updateContacts;
  $('create').onsubmit=e=>{e.preventDefault();change({action:'create',name:$('name').value},'name');};
  $('post').onsubmit=e=>{e.preventDefault();change({action:'post',text:$('text').value},'text');};
  $('password-form').onsubmit=e=>{e.preventDefault();change({action:'password',password:$('room-password').value},'room-password');};
  $('toggle').onclick=()=>change({action:'enabled',enabled:!Boolean(current().enabled)});
  $('delete-room').onclick=()=>{
    const room=current();
    if(!room || busy || room.enabled || room.is_bot)return;
    if(!window.confirm('Permanently delete room "'+room.name+'"?\n\nIts identity, password, participants, messages and history will be deleted. This cannot be undone.'))return;
    change({action:'delete',confirm_delete:true,expected:{name:room.name,public_key:room.public_key}});
  };
  $('bot-channel').onclick=()=>change({action:'bot'});
  $('restart').onclick=()=>change({action:'restart'});
  $('copy').onclick=async()=>{try {await navigator.clipboard.writeText(current().contact_uri);}catch { $('error').textContent='Copy this link: '+current().contact_uri; }};
  $('room').onchange=()=>{selected=Number($('room').value);render({rooms,status:lastStatus},true);};
  let lastStatus={running:false,sessions:0,dropped_packets:0};
  async function refresh(first=false){if(busy||document.hidden)return;busy=true;updateRoomActions();try{const result=await request();lastStatus=result.status;render(result,first);}catch(e){$('error').textContent=e.message;}finally{busy=false;updateRoomActions();}}
  if(embedded) {
    const resize=()=>{
      if(window.parent===window)return;
      const shell=document.querySelector('.room-shell');
      if(!shell)return;
      // Only measure the actual content, never body/documentElement scrollHeight:
      // those can inherit the iframe's previous height and create empty space.
      const height=Math.max(shell.getBoundingClientRect().height,shell.scrollHeight);
      if(height>0)window.parent.postMessage({kind:'meshcorestation-room-iframe-height',height:Math.ceil(height)+8},window.location.origin);
    };
    if(typeof ResizeObserver==='function')new ResizeObserver(resize).observe(document.querySelector('.room-shell'));
    window.addEventListener('load',resize);
    resize();
  }
  refresh(true);updateContacts();setInterval(()=>refresh(),5000);
})();
