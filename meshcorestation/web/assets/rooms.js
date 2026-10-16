/* Independent room dashboard; never inserts message content as HTML. */
(() => {
  'use strict';
  if (location.pathname !== '/rooms') return;
  const $ = id => document.getElementById(id);
  let rooms = [], selected = null, busy = false;
  let contacts = [], contactsLoaded = false, qrRoom = null, shownRoom = null;
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
  function renderContacts() {
    const picker=$('contact-picker'), previous=picker.value;
    const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=contactsLoaded?'Select a companion…':'Load contacts to choose a companion';
    const members=new Set((current()?.members || []).map(m=>m.public_key.toLowerCase()));
    picker.replaceChildren(placeholder,...contacts.map(c=>{
      const option=document.createElement('option');option.value=c.public_key;
      option.disabled=members.has(c.public_key);
      option.textContent=`${c.name || 'Unnamed'} · ${c.public_key.slice(0,12)}${option.disabled?' · Already a member':''}`;
      return option;
    }));
    if (contacts.some(c=>c.public_key===previous) && !members.has(previous)) picker.value=previous;
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
      $('show-qr').textContent='Show room QR code'; $('member-key').value=''; $('room-password').value='';
    }
    if (full) renderContacts();
    if (!room) return;
    $('title').textContent = room.name; $('state').textContent = room.enabled ? 'Enabled' : 'Disabled · no room radio traffic';
    $('toggle').textContent = room.enabled ? 'Disable room' : 'Enable room'; $('send').disabled = !room.enabled;
    $('bot-channel').textContent = room.is_bot ? 'Bot channel ✓' : 'Use as bot channel';
    $('public-key').value = room.public_key; $('import').href = room.contact_uri;
    $('password-state').textContent=room.auth_revision ? 'Password is set. Enter a new password only to change it.' : 'Set a password, then enable this room. Existing history and identity are preserved.';
    $('toggle').disabled=!room.auth_revision;
    $('members').replaceChildren(...room.members.filter(m=>m.public_key!==room.public_key).map(m => {
      const li=document.createElement('li'), span=document.createElement('span'), button=document.createElement('button');
      span.textContent=m.public_key+' · '+m.role;button.textContent='Remove';button.type='button';button.onclick=()=>change({action:'revoke',key:m.public_key});li.append(span,button);return li;
    }));
    $('posts').replaceChildren(...room.posts.map(p => {
      const row=document.createElement('article'), label=document.createElement('small'), text=document.createElement('p');
      label.textContent=new Date(p.timestamp*1000).toLocaleString()+' · '+(p.author===room.public_key?'Room':p.author.slice(0,12));label.title=p.author;text.textContent=p.text;row.append(label,text);return row;
    }));
    if (!room.posts.length) $('posts').textContent='No messages yet.';
  }
  async function change(body, clear) {
    if (busy) return;busy=true;$('error').textContent='';
    try {render(await request({room:selected,...body}),true);if(clear)$(clear).value='';}
    catch(e){$('error').textContent=e.message;}
    finally {busy=false;}
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
  $('load-contacts').onclick=async()=>{
    $('load-contacts').disabled=true; $('contact-status').textContent='Loading companion contacts…';
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),25000);
    try {
      const response=await fetch('/api/companion/contacts',{headers:{'X-Meshcore-Control':'1'},cache:'no-store',signal:controller.signal});
      const result=await response.json();
      if (!response.ok || !result.ok) throw Error(result.error || 'Could not load contacts');
      contacts=(result.contacts || []).filter(c=>Number(c.type)===1 && /^[0-9a-f]{64}$/i.test(c.public_key)).map(c=>({...c,public_key:c.public_key.toLowerCase()}));
      contacts.sort((a,b)=>(a.name || '').localeCompare(b.name || ''));
      contactsLoaded=true;renderContacts();
      $('contact-status').textContent=contacts.length?'Select a contact, choose permission, then click Add / update member.':'No companion contacts found. You can still enter a public key below.';
    } catch(e) { $('contact-status').textContent=e.message; }
    finally { clearTimeout(timeout); $('load-contacts').disabled=false; }
  };
  $('contact-picker').onchange=()=>{ $('member-key').value=$('contact-picker').value; };
  $('create').onsubmit=e=>{e.preventDefault();change({action:'create',name:$('name').value},'name');};
  $('grant').onsubmit=e=>{e.preventDefault();change({action:'grant',key:$('member-key').value.trim(),role:$('role').value},'member-key');};
  $('post').onsubmit=e=>{e.preventDefault();change({action:'post',text:$('text').value},'text');};
  $('password-form').onsubmit=e=>{e.preventDefault();change({action:'password',password:$('room-password').value},'room-password');};
  $('toggle').onclick=()=>change({action:'enabled',enabled:!Boolean(current().enabled)});
  $('bot-channel').onclick=()=>change({action:'bot'});
  $('restart').onclick=()=>change({action:'restart'});
  $('copy').onclick=async()=>{try {await navigator.clipboard.writeText(current().contact_uri);}catch { $('error').textContent='Copy this link: '+current().contact_uri; }};
  $('room').onchange=()=>{selected=Number($('room').value);render({rooms,status:lastStatus},true);};
  let lastStatus={running:false,sessions:0,dropped_packets:0};
  async function refresh(first=false){if(busy||document.hidden)return;busy=true;try{const result=await request();lastStatus=result.status;render(result,first);}catch(e){$('error').textContent=e.message;}finally{busy=false;}}
  refresh(true);setInterval(()=>refresh(),5000);
})();
