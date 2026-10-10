import asyncio
import time
import hashlib
import hmac
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from Crypto.Cipher import AES
from flask import Flask
from meshcore import EventType
from meshcorestation.storage import database,reply_store as store

KEY=b'1234567890123456'


@pytest.fixture
def db(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_FILE',tmp_path/'test.db')
    instance=database.Database(Mock())
    conn=instance.db
    conn.execute("INSERT INTO logger (id,sender,message) VALUES (1,'Alice','ping')")
    for key,name in [('aa'+'11'*31,'Repeater A'),('bb'+'22'*31,'Repeater B'),('bb'+'33'*31,'Collision')]:
        conn.execute('INSERT INTO repeaters(public_key,name,first_seen,last_seen) VALUES (?,?,1,1)',(key,name))
    conn.commit()
    yield instance
    instance.close()


def packet(text='Station: pong',stamp=1000,path='aa',scope=None,key=KEY):
    clear=stamp.to_bytes(4,'little')+b'\0'+text.encode()
    clear+=bytes((-len(clear))%16)
    cipher=AES.new(key,AES.MODE_ECB).encrypt(clear)
    payload=hashlib.sha256(key).digest()[:1]+hmac.new(key,cipher,hashlib.sha256).digest()[:2]+cipher
    result=dict(route_type=0 if scope else 1,payload_type=5,path_len=len(path)//2,path_hash_size=1,
                path=path,pkt_payload=payload,rssi=-100,snr=3)
    if scope:
        code=int.from_bytes(hmac.new(scope,b'\x05'+payload,hashlib.sha256).digest()[:2],'little')
        code=1 if code==0 else 65534 if code==65535 else code
        result['transport_code']=(code.to_bytes(2,'little')*2).hex()
    return result


def begin(conn,**kw):
    return store.begin(conn,1,'pong','Station',KEY,1000,'unscoped',kw.get('scope'),now=1000)


def test_matching_route_duplicates_and_collisions(db):
    conn=db.db;r=begin(conn)
    store.observe(conn,packet(path='aabbcc'),KEY,[],now=1002)
    store.finish(conn,r,'accepted')
    store.observe(conn,packet(path='aabbcc'),KEY,[],now=1003)
    observations=store.snapshot(conn,1)['replies'][0]['observations']
    assert len(observations)==1 and observations[0]['latency']==2
    assert [h['status'] for h in observations[0]['route']]==['forwarding observed','ambiguous repeater','unknown repeater']
    assert observations[0]['rssi']==-100


@pytest.mark.parametrize('change',[
    {'text':'Station: other'},{'text':'Other: pong'},{'stamp':999},{'key':b'abcdefghijklmnop'},
    {'path':''},{'scope':b'abcdefghijklmnop'}
])
def test_no_false_matches(db,change):
    begin(db.db)
    store.observe(db.db,packet(**change),KEY,[],now=1002)
    assert not store.snapshot(db.db,1)['replies'][0]['observations']


def test_mac_expiry_rejected_and_indistinguishable_sends(db):
    conn=db.db;r=begin(conn);p=packet()
    p['pkt_payload']=p['pkt_payload'][:1]+b'xx'+p['pkt_payload'][3:]
    store.observe(conn,p,KEY,[],now=1002)
    store.observe(conn,packet(),KEY,[],now=1301)
    store.finish(conn,r,'rejected');store.observe(conn,packet(),KEY,[],now=1002)
    assert not store.snapshot(conn,1)['replies'][0]['observations']
    store.finish(conn,r,'accepted');begin(conn)
    store.observe(conn,packet(),KEY,[],now=1002)
    assert all(not r['observations'] for r in store.snapshot(conn,1)['replies'])


def test_scoped_match_and_bounded_storage(db):
    secret=b'abcdefghijklmnop';begin(db.db,scope=secret)
    scopes=[{'scope_key':secret.hex()}]
    for i in range(80):
        store.observe(db.db,packet(path=f'{i:02x}',scope=secret),KEY,scopes,now=1002)
    result=store.snapshot(db.db,1)
    assert len(result['replies'][0]['observations'])==64
    assert secret.hex() not in str(result) and KEY.hex() not in str(result)


def test_command_ack_and_final_reply_link_before_echo(db):
    from meshcorestation.radio.companion import Companion
    async def scenario():
        c=Companion(Mock(),db);c.channel_idx=0;c.tracking_key=KEY
        c._find_matching_rx=lambda msg:{'route_type':1}
        calls=[]
        async def set_scope(scope):return NS(type=EventType.OK)
        async def send(channel,message,timestamp):
            calls.append((message,timestamp))
            store.observe(db.db,packet(text='Station: '+message,stamp=timestamp),KEY,[],now=time.time()+.1)
            return NS(type=EventType.OK)
        c.mc=NS(self_info={'name':'Station'},commands=NS(set_flood_scope=set_scope,send_chan_msg=send))
        async def handle(*args):
            await c.send_channel_message(0,'request received',{'route_type':1})
            return 'pong'
        c.bot=NS(match_command=lambda msg:{'trigger':'ping'},handle_message=handle)
        await c._process_channel_message(NS(payload={'channel_idx':0,'text':'Alice: ping','sender_timestamp':900,'recv_time':1000,'path_len':0}))
        command_id=db.db.execute('SELECT max(id) FROM logger').fetchone()[0]
        rows=store.snapshot(db.db,command_id)['replies']
        assert [r['message'] for r in rows]==['request received','pong']
        assert all(r['send_status']=='accepted' for r in rows)
        assert all(r['observations'] for r in rows)
        assert c.active_command_id is None
    asyncio.run(scenario())


def test_reply_api(db,monkeypatch):
    from meshcorestation.web import reply_api
    monkeypatch.setattr(reply_api,'DB_PATH',database.DB_FILE)
    app=Flask(__name__);reply_api.register_reply_routes(app)
    client=app.test_client();headers={'X-Meshcore-Control':'1'}
    assert client.get('/api/replies/1').status_code==403
    assert client.get('/api/replies/2',headers=headers).status_code==404
    begin(db.db)
    result=client.get('/api/replies/1',headers=headers)
    assert result.status_code==200
    assert result.json['replies'][0]['send_status']=='submitting'
    assert 'channel_key_hash' not in str(result.json)
