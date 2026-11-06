"""Opt-in, paced, read-only neighbor requests sharing the Companion control lock."""
import asyncio
from contextlib import closing
from pathlib import Path
import time
import uuid
from meshcorestation.storage import neighbor_snr as store
from meshcorestation.storage.connection import connect
from meshcorestation.radio.repeater_transport import RepeaterTransport,TIMEOUT

PAGE_SIZE=15
MAX_PAGES=128
REQUEST_GAP=5.0


class NeighborMonitor:
    def __init__(self,runtime,path):
        self.runtime,self.path=runtime,Path(path)
        self.task=None;self.last_request=0;self.collecting=False

    def start(self):
        self.task=asyncio.create_task(self.run(),name='neighbor-snr-monitor')

    async def close(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None

    def connected(self,companion):
        return companion is not None and self.runtime.companion is companion and self.runtime.control is not None and companion.mc.connection_manager.is_connected

    async def active(self,companion,cfg):
        return self.connected(companion) and await asyncio.to_thread(store.still_enabled,self.path,cfg)

    async def exchange(self,companion,cfg,call):
        await asyncio.sleep(max(0,self.last_request+REQUEST_GAP-time.monotonic()))
        async with companion.control_lock:
            if not await self.active(companion,cfg):raise ValueError('Monitoring disabled, repeater removed or Companion disconnected.')
            self.last_request=time.monotonic()
            return await asyncio.wait_for(call(),TIMEOUT+10)

    async def poll(self,cfg):
        companion=self.runtime.companion
        if not self.connected(companion):return
        if not await asyncio.to_thread(store.claim,self.path,cfg,time.time()):return
        poll_id=uuid.uuid4().hex;error='';self.collecting=True
        try:
            transport=RepeaterTransport(companion)
            login_data={}
            async def prepare():
                nonlocal login_data
                contact=await transport.contact(cfg['public_key'])
                if not await self.active(companion,cfg):raise ValueError('Monitoring configuration changed.')
                login_data=await transport.login(contact,'') # guest access only, no stored/admin passwords
                return contact
            contact=await self.exchange(companion,cfg,prepare)
            from meshcorestation.radio.averaged_snr_collection import collect
            if await collect(self,companion,cfg,contact,login_data,poll_id):return
            offset=0
            for _ in range(MAX_PAGES):
                started=time.time()
                # Capturing start inside the lock excludes scheduler/queue wait
                # from source-event uncertainty bounds.
                async def page():
                    nonlocal started
                    started=time.time()
                    return await companion.mc.commands.req_neighbours_sync(contact,count=PAGE_SIZE,offset=offset,timeout=TIMEOUT)
                data=await self.exchange(companion,cfg,page);received=time.time()
                if received<started:raise ValueError('System clock changed during collection; no SNR sample attributed.')
                if not isinstance(data,dict) or str(data.get('pubkey_prefix','')).lower()!=cfg['public_key'][:12]:
                    raise ValueError('No matching neighbor response; repeater may be unreachable or guest access unsupported.')
                rows=data.get('neighbours');total=data.get('neighbours_count');count=data.get('results_count')
                if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows) or type(total) is not int or not 0<=total<=32767 or type(count) is not int or count!=len(rows) or len(rows)>PAGE_SIZE:
                    raise ValueError('Malformed neighbor page; saved history is preserved.')
                if not await asyncio.to_thread(store.record_page,self.path,cfg,poll_id,started,received,rows):
                    raise ValueError('Monitoring configuration changed; remaining pages cancelled.')
                offset+=len(rows)
                if offset>=total:break
                if not rows:raise ValueError('Neighbor pagination stopped early; this poll is incomplete.')
            else:raise ValueError('Neighbor page safety limit reached; this poll is incomplete.')
        except asyncio.CancelledError:
            error='Monitoring interrupted; no automatic retry before the scheduled interval.'
            raise
        except asyncio.TimeoutError:
            error='Neighbor request timed out; no retry before the next scheduled interval.'
        except Exception as exc:
            error=str(exc) or type(exc).__name__
            self.runtime.logger.warning('Neighbor monitoring %s: %s',cfg['public_key'][:12],error)
        finally:
            self.collecting=False
            try:await asyncio.to_thread(store.finish,self.path,cfg,poll_id,time.time(),error[:300])
            except Exception as exc:self.runtime.logger.warning('Saving neighbor monitor status: %s',type(exc).__name__)

    async def tick(self):
        if not self.connected(self.runtime.companion):return
        pending=await asyncio.to_thread(store.due,self.path,time.time())
        if pending:await self.poll(pending[0]) # one repeater per tick; oldest due first

    async def run(self):
        def recover():
            with closing(connect(self.path,timeout=.25)) as db,db:
                db.execute("UPDATE neighbor_monitor SET state='interrupted',error='Previous collection interrupted; next scheduled interval is preserved.' WHERE state='collecting'")
        try:await asyncio.to_thread(recover)
        except Exception as exc:self.runtime.logger.warning('Neighbor monitor recovery: %s',type(exc).__name__)
        while True:
            try:await self.tick()
            except asyncio.CancelledError:raise
            except Exception as exc:self.runtime.logger.warning('Neighbor monitor: %s',type(exc).__name__)
            await asyncio.sleep(10)
