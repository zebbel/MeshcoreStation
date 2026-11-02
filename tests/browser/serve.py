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
    for i in range(205):db.add_logger({'message':'ping' if i%2 else 'status','name':'Fixture Sender','recv_time':2000000000+i},None,'unscoped','Fixture reply')
    runtime=Runtime(logging.getLogger('fixture'),db);runtime.companion=c;runtime.control=CompanionControl(c)
    runtime.device_info={'ver':'fixture','fw_build':'SIMULATED — no radio','model':'Fixture Companion'}
    bridge.attach(runtime);bridge.status=('Running','Fixture Companion connected — simulated hardware','running')
    updater.check=lambda branch=None:{'branch':'V5','available':False,'ready':False,'latest':'b'*40,'latest_version':'5.0.0','checked_at':2000000000}
    updater.ready=lambda:False
    bot_runtime.ports=lambda:[{'device':'/dev/fixture','description':'Simulated Companion'}]
    web=WebServer();web.start()
    try:await asyncio.Event().wait()
    finally:web.close();await c.disconnect();bridge.detach();db.close()

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='meshcorestation-v5-browser-',dir=os.environ.get('TMPDIR')) as directory:
        os.environ['MESHCORESTATION_DATA_DIR']=directory
        asyncio.run(run())
