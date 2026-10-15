/* Independent room dashboard; never inserts message content as HTML. */
(() => {
  'use strict';
  if (location.pathname !== '/rooms') return;
  const $ = id => document.getElementById(id);
  let rooms = [], selected = null, busy = false;
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
  function render(result, full) {
    rooms = result.rooms; lastStatus = result.status;
    if (!rooms.some(r => r.id === selected)) selected = rooms[0]?.id ?? null;
    $('status').textContent = (result.status.running ? 'Room worker ready' : 'Room worker stopped') + ` · ${result.status.sessions} connected members · ${result.status.dropped_packets} dropped input packets` + (result.status.error ? ' · '+result.status.error : '');
    if (full) {
      $('room').replaceChildren(...rooms.map(r => {const option = document.createElement('option');option.value=r.id;option.textContent=r.name+(r.enabled?' · enabled':' · disabled');return option;}));
      $('room').value = selected;
    }
    const room = current(); $('details').hidden = !room;
    if (!room) return;
    $('title').textContent = room.name; $('state').textContent = room.enabled ? 'Enabled' : 'Disabled · no room radio traffic';
    $('toggle').textContent = room.enabled ? 'Disable room' : 'Enable room'; $('send').disabled = !room.enabled;
    $('public-key').value = room.public_key; $('import').href = room.contact_uri;
    if (full) $('scope').value = room.scope_key;
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
  $('create').onsubmit=e=>{e.preventDefault();change({action:'create',name:$('name').value},'name');};
  $('grant').onsubmit=e=>{e.preventDefault();change({action:'grant',key:$('member-key').value.trim(),role:$('role').value},'member-key');};
  $('post').onsubmit=e=>{e.preventDefault();change({action:'post',text:$('text').value},'text');};
  $('scope-form').onsubmit=e=>{e.preventDefault();change({action:'scope',scope_key:$('scope').value.trim()});};
  $('toggle').onclick=()=>change({action:'enabled',enabled:!Boolean(current().enabled)});
  $('restart').onclick=()=>change({action:'restart'});
  $('copy').onclick=async()=>{try {await navigator.clipboard.writeText(current().contact_uri);}catch { $('error').textContent='Copy this link: '+current().contact_uri; }};
  $('room').onchange=()=>{selected=Number($('room').value);render({rooms,status:lastStatus},true);};
  let lastStatus={running:false,sessions:0,dropped_packets:0};
  async function refresh(first=false){if(busy||document.hidden)return;busy=true;try{const result=await request();lastStatus=result.status;render(result,first);}catch(e){$('error').textContent=e.message;}finally{busy=false;}}
  refresh(true);setInterval(()=>refresh(),5000);
})();
