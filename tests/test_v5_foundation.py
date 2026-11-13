"""V5 ownership, device parity and fresh dashboard acceptance checks."""
import asyncio
from contextlib import closing
import logging
from pathlib import Path
import sqlite3
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from dash import html
from meshcorestation import config
from meshcorestation.storage import database,registry
from meshcorestation.radio.companion import Companion
from meshcorestation.radio.companion_control import CompanionControl
from meshcorestation.radio.contacts_control import handle_contacts
from meshcorestation.radio.channels_control import handle_channels
from meshcorestation.web import data,voltage_api,commands_api,scopes_api,reply_api,bot_runtime
from fake_companion import FakeMeshCore,KEY,OTHER,IDENTITY


@pytest.fixture
def station(tmp_path,monkeypatch):
    path=tmp_path/'meshcorestation.db'
    for module,attr in [(database,'DB_FILE'),(config,'DB_PATH'),(data,'DB_PATH'),(voltage_api,'DB_PATH'),(commands_api,'DB_PATH'),(scopes_api,'DB_PATH'),(reply_api,'DB_PATH'),(bot_runtime,'DB_PATH')]:monkeypatch.setattr(module,attr,path)
    owner=database.Database(logging.getLogger('test'))
    yield owner
    owner.close()


def companion(owner):
    c=Companion(logging.getLogger('test'),owner);c.mc=FakeMeshCore();c.tracking_key=c.mc.channels[0][1]
    return c


def test_fresh_two_database_ownership_permissions_and_no_excluded_tables(station):
    path=database.DB_FILE
    assert {p.name for p in path.parent.glob('*.db')}=={'meshcorestation.db','knownRepeaters.db'}
    tables={r[0] for r in station.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'repeaters' not in tables and not {'measurements','network_observations','rooms','analyzer_cache'}&tables
    assert {'bot_settings','bot_commands','logger','command_replies','management_audit','application_preferences','voltage_config','voltage_samples'}<=tables
    for p in path.parent.glob('*.db'):assert p.stat().st_uid==path.stat().st_uid and p.stat().st_mode&0o077==0


def test_registry_contact_vs_actual_advert_count_dedup_and_validation(station):
    contact=dict(type=2,public_key=KEY.upper(),adv_name='Hill',adv_lat=49.6,adv_lon=8.6)
    for _ in range(3):station.add_new_repeater(NS(payload=contact),observed=False)
    row=station.db.execute('SELECT * FROM repeaters').fetchone()
    assert row['advert_count']==0 and row['source']=='contact' and row['last_seen']==0
    station.add_new_repeater(NS(payload={**contact,'adv_name':'New name'}),observed=True)
    assert station.get_repeater_count()==1 and station.get_repeater_advert_count(KEY)==1
    row=station.db.execute('SELECT * FROM repeaters').fetchone();assert row['name']=='New name' and row['source']=='advertisement'
    assert not station.add_new_repeater(NS(payload={**contact,'public_key':'abcd'}))
    assert not station.add_new_repeater(NS(payload={**contact,'type':1,'public_key':OTHER}))
    assert station.get_repeater_count()==1
    with pytest.raises(sqlite3.OperationalError):station.db.execute('DELETE FROM repeaters')


def test_companion_contacts_exact_validation_duplicates_deletion_and_readback(station):
    async def run():
        c=companion(station)
        before=await handle_contacts(c,{'operation':'get_contacts'})
        assert before['contacts'][0]['details']['repeater']['public_key']==KEY
        value={'public_key':OTHER,'name':'Second','type':2,'latitude':50,'longitude':9}
        add={'operation':'add_contact','expected_public_key':IDENTITY,'value':value}
        assert (await handle_contacts(c,add))['ok']
        assert not (await handle_contacts(c,add))['ok']
        stale={**add,'expected_public_key':'ff'*32,'value':{**value,'public_key':'ee'*32}}
        assert not (await handle_contacts(c,stale))['ok']
        with pytest.raises(ValueError):await handle_contacts(c,{**add,'value':{**value,'public_key':'bad'}})
        target=next(v for v in (await handle_contacts(c,{'operation':'get_contacts'}))['contacts'] if v['public_key']==OTHER)
        delete={'operation':'delete_contact','expected_public_key':IDENTITY,'public_key':OTHER,'expected':{k:v for k,v in target.items() if k!='details'},'confirm_delete':True}
        assert (await handle_contacts(c,delete))['ok']
        assert station.get_repeater_count()==2 # Removing a hardware contact doesn't erase the registry.
        c.mc.commands.ignore_writes=True
        assert not (await handle_contacts(c,add))['ok']
    asyncio.run(run())


def test_channels_bot_selection_protection_private_key_nonpersistence_and_readback(station):
    async def run():
        c=companion(station)
        async def read():return await handle_channels(c,{'operation':'get_channels'})
        state=await read()
        def request(operation,**body):return {'operation':operation,'expected_public_key':IDENTITY,'expected_revision':state['revision'],**body}
        assert (await handle_channels(c,request('set_bot_channel',index=0)))['ok']
        assert c.channel_idx==0 and station.get_bot_settings()['channel_name']=='Bot'
        state=await read();assert state['channels'][0]['protected']
        with pytest.raises(ValueError):await handle_channels(c,request('delete_channel',index=0,confirm_delete=True))
        secret='34567890abcdef12'*2
        add=request('add_channel',value={'name':'Private','type':'private','secret':secret})
        assert (await handle_channels(c,add))['ok']
        assert not (await handle_channels(c,add))['ok'] # Old revision is rejected.
        state=await read();assert state['capacity']==8 and state['free_slots']==6
        assert secret not in str(state) and secret not in '\n'.join(station.db.iterdump())
        c.mc.commands.ignore_writes=True
        assert not (await handle_channels(c,request('delete_channel',index=1,confirm_delete=True)))['ok']
        c.mc.commands.ignore_writes=False
        assert (await handle_channels(c,request('delete_channel',index=1,confirm_delete=True)))['ok']
    asyncio.run(run())


def test_companion_settings_validation_stale_values_and_readback(station):
    async def run():
        c=companion(station);control=CompanionControl(c)
        before=(await control.execute({'operation':'get'}))['settings']
        assert not (await control.execute({'operation':'name','expected':{**before,'name':'stale'},'value':'New'}))['ok']
        assert (await control.execute({'operation':'name','expected':before,'value':'New'}))['ok']
        before=(await control.execute({'operation':'get'}))['settings']
        c.mc.commands.ignore_writes=True
        assert not (await control.execute({'operation':'tx_power','expected':before,'value':12}))['ok']
        with pytest.raises(ValueError):await control.execute({'operation':'radio','expected':before,'value':{'freq':869.525,'bw':125,'sf':7,'cr':5}})
    asyncio.run(run())


def test_history_200_pagination_filter_oldest_order_and_restart(station):
    for i in range(405):station.add_logger({'message':'ping' if i%2 else 'status','name':'Alice','recv_time':i},None,'unscoped','pong')
    first=data.snapshot();older=data.snapshot(limit=400);filtered=data.snapshot('ping')
    assert len(first['rows'])==200 and first['rows'][0]['recv_time']==205 and first['rows'][-1]['recv_time']==404
    assert len(older['rows'])==400 and older['rows'][0]['recv_time']==5
    assert filtered['total']==202 and all(r['message']=='ping' for r in filtered['rows'])
    reopened=database.Database(logging.getLogger('test'));assert reopened.db.execute('SELECT count(*) FROM logger').fetchone()[0]==405;reopened.close()


def test_http_preferences_commands_scopes_managed_removal_offline_map_and_exclusions(station,monkeypatch):
    from meshcorestation.web.app import create_app
    from meshcorestation import display
    from meshcorestation.bridge import bridge
    bridge.detach()
    station.add_new_repeater(NS(payload={'type':2,'public_key':KEY,'adv_name':'Hill','adv_lat':49.6,'adv_lon':8.6}),observed=False)
    c=create_app().server.test_client();h={'X-Meshcore-Control':'1'}
    assert c.get('/api/companion',headers=h).status_code==503
    assert c.get('/api/maps/repeaters').json['nodes'][0]['label']=='Hill'
    assert c.post('/api/display-settings',headers=h,json={'date_format':'iso','hour_format':'12'}).status_code==200
    assert display.settings()=={'date_format':'iso','hour_format':'12'}
    assert c.post('/api/bot/voltage',headers=h,json={'operation':'add','public_key':KEY}).json['ok']
    assert KEY in c.get('/api/bot/voltage?days=1',headers=h).json['managed_repeaters']
    assert c.post('/api/bot/voltage',headers=h,json={'operation':'remove','public_key':KEY}).json['ok']
    assert KEY not in c.get('/api/bot/voltage?days=1',headers=h).json['managed_repeaters']
    assert station.get_repeater_count()==1
    commands=c.get('/api/bot/commands',headers=h).json
    bad=c.post('/api/bot/commands',headers=h,json={'operation':'save','commands':[],'expected_revision':commands['revision']})
    assert bad.status_code==400
    scopes=c.get('/api/bot/scopes',headers=h).json
    add=c.post('/api/bot/scopes',headers=h,json={'operation':'add','name':'local','expected_revision':scopes['revision']})
    assert add.status_code==200 and len(add.json['scopes'])==1
    rules={rule.rule for rule in c.application.url_map.iter_rules()}
    assert c.get('/rooms').status_code == 200
    for path in ['/repeater-optimizer','/api/repeater-network','/api/repeater-performance']:
        assert c.get(path).status_code==404
    assert not {'/api/repeater-network','/api/repeater-performance','/repeater-optimizer','/api/repeater-statistics'}&rules
    assert {p.name for p in database.DB_FILE.parent.glob('*.db')}=={'meshcorestation.db','knownRepeaters.db'}


def walk(node):
    yield node
    children=getattr(node,'children',[])
    if not isinstance(children,list):children=[children]
    for child in children:
        if hasattr(child,'children'):yield from walk(child)


def test_exact_dashboard_structure_and_closed_history_no_reads(station,monkeypatch):
    from meshcorestation.web.app import create_app
    from meshcorestation.web.layout import build_layout
    from meshcorestation.web import callbacks
    page=build_layout();nodes=list(walk(page));ids={getattr(n,'id',None):n for n in nodes}
    cards=next(n for n in nodes if getattr(n,'className',None)=='cards')
    assert [c.id for c in cards.children]==['station-card','companion-card','known-card']
    sections=[n.children.id for n in page.children if isinstance(n,html.Section) and isinstance(n.children,html.Details)]
    assert sections==['bot-disclosure','room-server-disclosure','repeater-management-disclosure','repeater-statistics-disclosure','repeater-comparison-disclosure']
    assert ids['statistics-repeater'] is not ids['managed-repeater']
    bot=ids['bot-disclosure'];assert [n.id for n in walk(bot) if isinstance(n,html.Details)]==['bot-disclosure','bot-settings-disclosure','command-history-disclosure']
    ids_list=[n.id for n in nodes if getattr(n,'id',None)]
    assert len(ids_list)==len(set(ids_list))
    monkeypatch.setattr(callbacks,'history_snapshot',lambda *a:(_ for _ in ()).throw(AssertionError('Closed history read')))
    app=create_app();cb=next(v['callback'] for k,v in app.callback_map.items() if 'command-rows' in k)
    from dash import no_update
    assert cb.__wrapped__(0,None,200,False,None)==(no_update,)*8


def test_connection_reconnection_and_shutdown_use_one_session(station,monkeypatch):
    from meshcorestation import runtime as runtime_module
    from meshcorestation.radio import companion as companion_module
    from meshcorestation.bridge import bridge
    from unittest.mock import Mock
    async def run():
        radios=[];connected=asyncio.Event();count=0
        async def create(*args,**kwargs):
            radio=FakeMeshCore();radios.append(radio);return radio
        monkeypatch.setattr(companion_module.MeshCore,'create_serial',create)
        class Monitor:
            def __init__(self,c):pass
            def start(self):pass
            async def close(self):pass
        monkeypatch.setattr(runtime_module,'VoltageMonitor',Monitor)
        logger=Mock()
        def ready():connected.set()
        logger.set_log_level.side_effect=ready
        station.set_bot_channel('Bot')
        runtime=runtime_module.Runtime(logger,station)
        task=asyncio.create_task(runtime.run())
        try:
            await asyncio.wait_for(connected.wait(),2)
            assert runtime.companion.channel_idx==0
            connected.clear();runtime.reconnect_requested.set()
            await asyncio.wait_for(connected.wait(),2)
            assert len(radios)==2 and not radios[0].connection_manager.is_connected
            assert radios[1].connection_manager.is_connected
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
        assert not radios[-1].connection_manager.is_connected and bridge.runtime is None
        assert runtime.statistics.task.done() and not runtime.statistics.health()['running']
    asyncio.run(run())


def test_repeater_permissions_read_confirm_readback_and_secret_free_audit(station):
    async def run():
        c=companion(station);control=CompanionControl(c).repeaters
        remote={'name':'Hill repeater'}
        ignore=[False]
        async def cli(contact,text,**kwargs):
            if text.startswith('get '):return '> '+remote[text[4:]]
            if text.startswith('set '):
                _,field,value=text.split(' ',2)
                if not ignore[0]:remote[field]=value
                return 'OK'
            if text.startswith('password '):return 'password now: '+text[9:]
            return 'OK'
        control.transport.cli=cli
        guest=await control.execute({'action':'login','public_key':KEY,'password':''})
        base={'public_key':KEY,'session':guest['session']}
        with pytest.raises(ValueError):await control.execute({**base,'action':'read','field':'name'})
        admin=await control.execute({'action':'login','public_key':KEY,'password':'admin'})
        base['session']=admin['session']
        with pytest.raises(ValueError):await control.execute({**base,'action':'write','field':'name','value':'Changed','expected':'Hill repeater','confirm':True})
        read=await control.execute({**base,'action':'read','field':'name'});assert read['value']=='Hill repeater'
        with pytest.raises(ValueError):await control.execute({**base,'action':'write','field':'name','value':'Changed','expected':'Hill repeater','confirm':False})
        written=await control.execute({**base,'action':'write','field':'name','value':'Changed','expected':'Hill repeater','confirm':True})
        assert written['ok'] and written['value']=='Changed'
        ignore[0]=True
        failed=await control.execute({**base,'action':'write','field':'name','value':'Ignored','expected':'Changed','confirm':True})
        assert not failed['ok'] and failed['value']=='Changed'
        audits=[dict(row) for row in station.db.execute('SELECT * FROM management_audit ORDER BY id')]
        assert [row['status'] for row in audits]==['verified','different readback']
        secret='abc123-Secret'
        password=await control.execute({**base,'action':'write','field':'admin_password','value':secret,'confirm':True})
        assert password['ok'] and password['value']==''
        assert secret not in str(password) and secret not in '\n'.join(station.db.iterdump())
        audit=dict(station.db.execute('SELECT * FROM management_audit ORDER BY id DESC LIMIT 1').fetchone())
        assert audit['before_value'] is None and audit['after_value'] is None
        await control.execute({**base,'action':'logout'})
        assert (await control.execute({**base,'action':'status'}))['expired']
    asyncio.run(run())


def test_actual_rx_advert_registration_is_not_contact_or_notification_count(station):
    from meshcorestation.radio.repeater_sync import RepeaterSync
    c=companion(station);sync=RepeaterSync(c)
    contact=c.mc.contacts[KEY]
    sync.import_contacts(NS(payload={KEY:contact}))
    sync.advertisement(NS(payload={'public_key':KEY}))
    assert station.get_repeater_advert_count(KEY)==0
    payload=bytes.fromhex(KEY)+(123).to_bytes(4,'little')+bytes(64)+bytes([0x92])+b'Hill'
    rx={'payload_type':4,'adv_type':2,'adv_key':KEY,'adv_name':'Hill','adv_flags':0x92,'adv_timestamp':123,'adv_lat':49.6,'adv_lon':8.6,'pkt_payload':payload}
    c._handle_rx_log(NS(payload=rx))
    assert station.get_repeater_count()==1 and station.get_repeater_advert_count(KEY)==1
    sync.import_contacts(NS(payload={KEY:contact}))
    assert station.get_repeater_advert_count(KEY)==1
    c._handle_rx_log(NS(payload={**rx,'adv_key':OTHER}))
    assert station.get_repeater_count()==1 and station.get_repeater_advert_count(KEY)==1


@pytest.mark.parametrize('count', [55, 200, 405])
def test_history_uses_one_connection_and_skips_unchanged_render(station, monkeypatch, count):
    from dash import Dash, no_update
    from meshcorestation.web import callbacks

    with station.db:
        station.db.executemany('INSERT INTO logger (recv_time,message,sender_timestamp) VALUES (?,?,?)',
                               ((1700049600+i, 'ping' if i%2 else 'status', 1700049600) for i in range(count)))
    real = sqlite3.connect
    connections, sql = [], []

    def connect(*args, **kwargs):
        db = real(*args, **kwargs)
        connections.append(db)
        db.set_trace_callback(sql.append)
        return db

    monkeypatch.setattr(sqlite3, 'connect', connect)
    app = Dash(__name__)
    callbacks.register_callbacks(app)
    refresh = next(v['callback'].__wrapped__ for k,v in app.callback_map.items() if 'command-rows.children' in k)
    first = refresh(0, None, 200, True, None)
    assert len(first[1]) == min(200,count)
    assert len(connections) == 1 and len(first[6]) == 64
    assert all('ATTACH' not in statement.upper() for statement in sql)

    sql.clear()
    assert refresh(1, None, 200, True, first[6]) == (no_update,)*8
    assert len(connections) == 2
    assert len(sql) == 3 and all('FROM logger' not in statement for statement in sql)
    assert refresh(2, None, 200, False, first[6]) == (no_update,)*8
    assert len(connections) == 2

    assert len(refresh(2, 'ping', 200, True, first[6])[1]) == min(200,count//2)
    assert len(refresh(2, None, 400, True, first[6])[1]) == min(400,count)
    for date_format, date in [('german','15.11.2023'), ('iso','2023-11-15'), ('us','11/15/2023')]:
        for clock in ('12', '24'):
            with station.db:
                station.db.execute('UPDATE application_preferences SET date_format=?,hour_format=?',
                                   (date_format,clock))
            result = refresh(3,None,200,True,None)
            formatted = result[1][-1].children[0].children
            assert formatted.startswith(date)
            assert ('PM' in formatted or 'AM' in formatted) == (clock=='12')
    with station.db:
        station.db.execute("UPDATE logger SET reply='verified reply' WHERE id=?", (count,))
    updated = refresh(4,None,200,True,result[6])
    assert 'verified reply' in updated[1][-1].children[-1].children.to_plotly_json()['props']['data-details']


def test_local_registry_controls_preserve_history_and_rediscover_only_unblocked(station):
    from flask import Flask
    from meshcorestation.storage import passive_stats, repeater_comparison
    from meshcorestation.storage.voltage_store import ensure_repeater
    from meshcorestation.radio.repeater_sync import RepeaterSync
    from meshcorestation.web.map_routes import register_map_routes

    contact = dict(type=2, public_key=KEY, adv_name='Hill')
    assert station.add_new_repeater(NS(payload=contact))
    with station.db:
        ensure_repeater(station.db, KEY)
    packet = passive_stats.normalize(dict(route_type=1, payload_type=5, path=KEY[:2],
        path_len=1, path_hash_size=1, pkt_payload=b'fixture observation'))
    assert passive_stats.store_batch(database.DB_FILE, [packet])[0] == {KEY: 1}
    path = passive_stats.statistics_path(database.DB_FILE, KEY)
    station.add_logger(dict(message='ping', name='Fixture sender', recv_time=2000000000), None, 'unscoped', 'Fixture reply')
    repeater_comparison.mutate(database.DB_FILE, KEY, 'create', 'Fixture antenna change')
    original = {table: station.db.execute(f'SELECT * FROM {table}').fetchall()
                for table in ('logger', 'voltage_config', 'repeater_changes')}
    with closing(sqlite3.connect(path)) as history:
        observations = history.execute('SELECT * FROM observations').fetchall()

    app = Flask(__name__)
    register_map_routes(app)
    client = app.test_client()
    url = '/api/repeater-registry'
    control = {'X-Meshcore-Control': '1'}

    def action(name, public_key=KEY, confirm=True, headers=control):
        return client.post(url, json=dict(action=name, public_key=public_key, confirm=confirm), headers=headers)

    assert action('block', headers={}).status_code == 403
    assert action('delete', headers={**control, 'Origin': 'https://example.com'}).status_code == 403
    assert action('block', public_key=KEY[:8]).status_code == 400
    assert action('block', confirm=1).status_code == 400
    assert action('block').status_code == action('delete').status_code == 409
    assert original['voltage_config'] == station.db.execute('SELECT * FROM voltage_config').fetchall()
    assert client.get('/api/maps/repeaters').json['unlocated'][0]['managed']
    with station.db:
        station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?', (KEY,))

    assert action('delete', KEY.upper()).status_code == 200
    assert not client.get('/api/maps/repeaters').json['unlocated']
    assert client.get(url, headers=control).json['blocked'] == []
    assert station.add_new_repeater(NS(payload=contact))
    assert action('block').status_code == 200
    assert not client.get('/api/maps/repeaters').json['unlocated']
    assert client.get(url, headers=control).json['blocked'] == [dict(public_key=KEY, name='Hill')]
    assert not station.add_new_repeater(NS(payload=contact))

    restarted = database.Database(logging.getLogger('restart fixture'))
    try:
        assert not restarted.add_new_repeater(NS(payload=contact))
        device = companion(restarted)
        RepeaterSync(device).import_contacts(NS(payload={KEY: contact}))
        asyncio.run(handle_contacts(device, {'operation': 'get_contacts'}))
        assert restarted.get_repeater_count() == 0
        with restarted.db, pytest.raises(ValueError, match='known repeater'):
            ensure_repeater(restarted.db, KEY)
        assert action('unblock', confirm=False).status_code == 400
        assert action('unblock').status_code == 200
        assert restarted.get_repeater_count() == 0
        RepeaterSync(device).import_contacts(NS(payload={KEY: contact}))
        assert restarted.get_repeater_count() == 1
    finally:
        restarted.close()
    with closing(sqlite3.connect(path)) as history:
        assert history.execute('SELECT * FROM observations').fetchall() == observations
    for table in ('logger', 'repeater_changes'):
        assert station.db.execute(f'SELECT * FROM {table}').fetchall() == original[table]


@pytest.mark.parametrize('action', ['block', 'delete'])
def test_registry_discovery_serializes_with_visibility_change(station, action):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    contact = dict(type=2, public_key=KEY, adv_name='Concurrent discovery')
    assert registry.upsert(station.known_path, contact)
    start = Barrier(2)

    def discover():
        start.wait(timeout=5)
        return registry.upsert(station.known_path, contact)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(discover)
        start.wait(timeout=5)
        registry.change_visibility(database.DB_FILE, KEY, action)
        inserted = pending.result(timeout=5)
    if action == 'block':
        assert station.get_repeater_count() == 0
        assert not registry.upsert(station.known_path, contact)
    else:
        assert inserted
        assert registry.blocked_repeaters(station.known_path) == []
        assert registry.upsert(station.known_path, contact)


def test_registry_block_rolls_back_if_removal_fails(station):
    assert registry.upsert(station.known_path, dict(type=2, public_key=KEY, adv_name='Hill'))
    with closing(sqlite3.connect(station.known_path)) as db, db:
        db.execute("""CREATE TRIGGER fail_removal BEFORE DELETE ON repeaters
                      BEGIN SELECT RAISE(ABORT,'fixture failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        registry.change_visibility(database.DB_FILE, KEY, 'block')
    assert registry.blocked_repeaters(station.known_path) == []
    assert station.get_repeater_count() == 1


def test_registry_protection_serializes_with_management_add(station):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from meshcorestation.storage.connection import connect
    from meshcorestation.storage.voltage_store import MEMBERSHIP_LOCK, ensure_repeater

    assert registry.upsert(station.known_path, dict(type=2, public_key=KEY))
    ready = Barrier(2)

    def manage():
        with MEMBERSHIP_LOCK, closing(connect(database.DB_FILE)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            ensure_repeater(db, KEY)
            ready.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(manage)
        ready.wait(timeout=5)
        with pytest.raises(registry.ManagedRepeaterError):
            registry.change_visibility(database.DB_FILE, KEY, 'block')
        pending.result(timeout=5)
    assert registry.blocked_repeaters(station.known_path) == []
    assert station.get_repeater_count() == 1
