"""Local review fixture: synthetic observations, in-memory hardware; never RF."""
import asyncio,logging,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('MESHCORESTATION_HOST','127.0.0.1')
os.environ.setdefault('MESHCORESTATION_PORT','8050')

async def run():
    from meshcorestation.storage.database import Database
    from meshcorestation.storage.voltage_store import ensure_repeater
    from meshcorestation.radio.companion import Companion
    from meshcorestation.radio.companion_control import CompanionControl
    from meshcorestation.runtime import Runtime
    from meshcorestation.bridge import bridge
    from meshcorestation.web_server import WebServer
    from meshcorestation.web import bot_runtime
    from meshcorestation import updater
    from fake_companion import FakeMeshCore,KEY
    from types import SimpleNamespace as NS
    db=Database(logging.getLogger('fixture'));c=Companion(logging.getLogger('fixture'),db)
    c.mc=FakeMeshCore();c.mc.channels[1]=('Alternate Bot',bytes.fromhex('34'*16));c.channel_idx=0;c.channel_name='Bot';c.tracking_key=c.mc.channels[0][1]
    db.set_bot_channel('Bot')
    for contact in c.mc.contacts.values():db.add_new_repeater(NS(payload=contact),observed=False)
    with db.db:ensure_repeater(db.db,KEY)
    # Synthetic passive observations exercise charts and actual Leaflet overlays;
    # these are fixture-only records, never production/example measurements.
    from meshcorestation.storage import passive_stats
    from time import time_ns
    for key,name,latitude,longitude in [('cd'*32,'Fixture north',49.7,8.7),('ef'*32,'Fixture south',49.5,8.5)]:
        db.add_new_repeater(NS(payload=dict(type=2,public_key=key,adv_name=name,adv_lat=latitude,adv_lon=longitude)),observed=False)
    for index,path in enumerate(('abcd','cdab','abef')):
        packet=passive_stats.normalize(dict(payload_type=5,route_type=1,path_hash_size=1,path_len=2,path=path,pkt_payload=('fixture '+str(index)).encode()),now_ns=time_ns())
        passive_stats.store_batch(db.db.execute('PRAGMA database_list').fetchone()[2],[packet])
    from meshcorestation.storage import neighbor_snr
    import time
    main_path=db.db.execute('PRAGMA database_list').fetchone()[2]
    cfg=neighbor_snr.save_settings(main_path,KEY,True,30)
    stamp=time.time()
    for tag,started,age,snr in [('first',stamp-100,10,3),('same',stamp-50,60,3),('new',stamp-5,2,4.5)]:
        neighbor_snr.record_page(main_path,cfg,tag,started,started+1,[dict(pubkey='cdcdcdcd',secs_ago=age,snr=snr)])
    import json,struct
    from meshcorestation.radio.averaged_snr import decode
    from meshcorestation.storage import averaged_snr
    vectors=json.loads((Path(__file__).resolve().parents[1]/'fixtures/averaged_snr_v1.json').read_text())
    raw=bytearray.fromhex(vectors['example']);raw[64:96]=bytes.fromhex('ef'*32)
    struct.pack_into('<II',raw,112,int(stamp)-3600,int(stamp)-1800)
    header=decode(bytes(raw))
    averaged_snr.record(main_path,cfg,'firmware-fixture',stamp,header,bytes(raw))
    averaged_snr.finish_for(main_path,KEY,'firmware-fixture',True)
    averaged_snr.update(main_path,cfg,capability='averaged',detection='supported',session=header['session'],last_collection=stamp,
        last_window=int(stamp)-1800,records_retrieved=1,completeness='complete',diagnostics={k:v for k,v in header.items() if k!='record'})
    neighbor_snr.save_settings(main_path,KEY,False,30)
    for i in range(205):db.add_logger({'message':'ping' if i%2 else 'status','name':'Fixture Sender','recv_time':2000000000+i},None,'unscoped','Fixture reply')
    runtime=Runtime(logging.getLogger('fixture'),db);runtime.companion=c;runtime.control=CompanionControl(c)
    runtime.device_info={'ver':'fixture','fw_build':'SIMULATED — no radio','model':'Fixture Companion'}
    # Manual reads use real client frame construction and fake completed-window
    # replies. The disabled automatic monitor never generates scheduled traffic.
    from types import MethodType
    from meshcore import EventType
    from meshcore.commands.base import CommandHandlerBase
    from meshcorestation.radio.averaged_snr import HEADER
    commands=c.mc.commands;original_send=commands.send
    commands._reader=None;commands._mesh_request_lock=asyncio.Lock()
    commands.send_binary_req=MethodType(CommandHandlerBase.send_binary_req,commands)
    async def binary_send(payload,*args,**kwargs):
        if payload and payload[0]==0x32:
            _,_,count,_,boot,ceiling,cursor=struct.unpack_from('<BBBB16sII',payload,33)
            values=list(HEADER.unpack_from(raw));has_record=bool(count and cursor<1)
            values[2]=int(has_record);values[3]=int(not has_record and cursor<1);values[5]=1;values[6]=1 if has_record else cursor
            answer=HEADER.pack(*values)+(bytes(raw[64:140]) if has_record else b'')
            for callback in list(c.mc.subscriptions.get(EventType.BINARY_RESPONSE,[])):
                await callback(NS(type=EventType.BINARY_RESPONSE,payload=dict(tag='12345678',data=answer.hex())))
            return NS(type=EventType.MSG_SENT,payload=dict(expected_ack=bytes.fromhex('12345678')))
        return await original_send(payload,*args,**kwargs)
    commands.send=binary_send
    runtime.neighbor_monitor.start()
    bridge.attach(runtime);bridge.status=('Running','Fixture Companion connected — simulated hardware','running')
    updater.check=lambda branch=None:{'branch':'V6','available':False,'ready':False,'latest':'b'*40,'latest_version':'6.0.0','checked_at':2000000000}
    updater.ready=lambda:False
    bot_runtime.ports=lambda:[{'device':'/dev/fixture','description':'Simulated Companion'}]
    web=WebServer();web.start()
    try:await asyncio.Event().wait()
    finally:web.close();await runtime.neighbor_monitor.close();await c.disconnect();bridge.detach();db.close()

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='meshcorestation-v5-browser-',dir=os.environ.get('TMPDIR')) as directory:
        os.environ['MESHCORESTATION_DATA_DIR']=directory
        asyncio.run(run())
