"""Opt-in, paced, read-only neighbor requests sharing the Companion control lock."""
import asyncio
from contextlib import closing
from pathlib import Path
import time
import uuid
from meshcorestation.storage import neighbor_snr as store
from meshcorestation.storage import neighbor_snr_manual as manual
from meshcorestation.radio.averaged_snr_collection import PartialCollection
from meshcorestation.storage.connection import connect
from meshcorestation.radio.repeater_transport import RepeaterTransport,TIMEOUT

PAGE_SIZE=15
MAX_PAGES=128
REQUEST_GAP=5.0


class NeighborMonitor:
    def __init__(self,runtime,path):
        self.runtime,self.path=runtime,Path(path)
        self.task=None;self.last_request=0;self.collecting=False
        self.collection_lock=asyncio.Lock();self.wakeup=asyncio.Event();self.ready=False

    def start(self):
        self.task=asyncio.create_task(self.run(),name='neighbor-snr-monitor')

    async def close(self):
        self.ready=False
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
        try:await asyncio.to_thread(manual.cancel_pending,self.path,'Companion disconnected or collector stopped; request a new read explicitly.')
        except Exception as exc:self.runtime.logger.warning('Saving interrupted manual SNR status: %s',type(exc).__name__)

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

    async def progress(self,cfg,text,records,protocol):
        if 'manual_job_id' in cfg:
            if not await asyncio.to_thread(manual.progress,self.path,cfg,text,records,protocol):
                raise asyncio.CancelledError('One-time collection authorization revoked.')

    async def poll(self,cfg):
        # One collector serves scheduled and explicitly authorized manual work.
        async with self.collection_lock:
            if 'job_id' not in cfg:
                return await self._poll(cfg)
            cfg=await asyncio.to_thread(manual.claim,self.path,cfg)
            if cfg is None:return
            operation=asyncio.create_task(self._poll(cfg))
            deadline=time.monotonic()+manual.MAX_SECONDS
            try:
                while not operation.done():
                    await asyncio.wait({operation},timeout=.25)
                    if not operation.done() and (time.monotonic()>deadline or not await self.active(self.runtime.companion,cfg)):
                        operation.cancel()
                await operation
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():raise
            finally:
                operation.cancel();await asyncio.gather(operation,return_exceptions=True)

    async def _poll(self,cfg):
        companion=self.runtime.companion
        if not self.connected(companion):
            if 'manual_job_id' in cfg:await asyncio.to_thread(manual.finish,self.path,cfg,'Companion disconnected before collection.')
            return
        if 'manual_job_id' not in cfg and not await asyncio.to_thread(store.claim,self.path,cfg,time.time()):return
        poll_id=cfg.get('manual_job_id') or uuid.uuid4().hex;error='';partial=False;self.collecting=True
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
                await self.progress(cfg,f'Received {offset} legacy neighbor rows (reported total {total}).',offset,'legacy')
                if offset>=total:break
                if not rows:raise ValueError('Neighbor pagination stopped early; this poll is incomplete.')
            else:raise ValueError('Neighbor page safety limit reached; this poll is incomplete.')
        except asyncio.CancelledError:
            error='Manual neighbor SNR read interrupted; request a new read explicitly.' if 'manual_job_id' in cfg else 'Monitoring interrupted; no automatic retry before the scheduled interval.'
            raise
        except asyncio.TimeoutError:
            error='Neighbor request timed out; saved records preserved. Request another read explicitly.' if 'manual_job_id' in cfg else 'Neighbor request timed out; no retry before the next scheduled interval.'
        except PartialCollection as exc:
            partial=True;error=str(exc)
        except Exception as exc:
            error=str(exc) or type(exc).__name__
            self.runtime.logger.warning('Neighbor monitoring %s: %s',cfg['public_key'][:12],error)
        finally:
            self.collecting=False
            try:await asyncio.to_thread(store.finish,self.path,cfg,poll_id,time.time(),error[:300])
            except Exception as exc:self.runtime.logger.warning('Saving neighbor monitor status: %s',type(exc).__name__)
            if 'manual_job_id' in cfg:
                try:await asyncio.to_thread(manual.finish,self.path,cfg,error,partial)
                except Exception as exc:self.runtime.logger.warning('Saving manual SNR status: %s',type(exc).__name__)

    async def tick(self):
        if not self.connected(self.runtime.companion):return
        one_time=await asyncio.to_thread(manual.pending,self.path)
        if one_time:
            await self.poll(one_time);return
        pending=await asyncio.to_thread(store.due,self.path,time.time())
        if pending:await self.poll(pending[0]) # one repeater per tick; oldest due first

    async def run(self):
        def recover():
            with closing(connect(self.path,timeout=.25)) as db,db:
                db.execute("UPDATE neighbor_monitor SET state='interrupted',error='Previous collection interrupted; next scheduled interval is preserved.' WHERE state='collecting'")
        self.ready=False
        while True:
            self.wakeup.clear()
            try:
                if not self.ready:
                    await asyncio.to_thread(recover)
                    await asyncio.to_thread(manual.cancel_pending,self.path,'Collector restarted; one-time reads are not replayed automatically.')
                    self.ready=True
                await self.tick()
            except asyncio.CancelledError:raise
            except Exception as exc:self.runtime.logger.warning('Neighbor monitor: %s',type(exc).__name__)
            try:await asyncio.wait_for(self.wakeup.wait(),10)
            except asyncio.TimeoutError:pass
