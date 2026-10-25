"""Bounded channel-reply retransmissions, never command re-execution or delivery ACKs."""
import asyncio
from collections import deque
from dataclasses import dataclass, field
import math
import random
import time
from meshcore import EventType
from meshcorestation.storage import reply_store

MAX_PENDING=32
MAX_RETRY_AIRTIME=60.0  # Additional RF airtime per rolling hour, per station session.
MAX_PACKET_AIRTIME=10.0
RADIO_FIELDS=('public_key','name','adv_name','radio_freq','radio_sf','radio_bw','radio_cr')


def timing(info,message,scoped):
    """MeshCore group framing + RadioLib explicit-header LoRa airtime, CRC enabled.

    Preamble: current MeshCore uses 32 symbols at SF <= 8, otherwise 16.
    Low-SF coefficients follow RadioLib SX126x; LDRO when symbol time >=16ms.
    BW is the Companion's reported kHz; CR is denominator 5..8 (4/5..4/8).
    """
    sf,bw,cr=(info.get(k) for k in ('radio_sf','radio_bw','radio_cr'))
    if type(sf) is not int or not 5<=sf<=12 or type(cr) is not int or not 5<=cr<=8 or type(bw) not in (int,float) or not math.isfinite(bw) or not 7.8<=bw<=500:
        raise ValueError('Actual Companion SF/BW/CR unavailable or unsupported; retries disabled.')
    name=info.get('name') or info.get('adv_name')
    if not isinstance(name,str) or not name or '\0' in message:
        raise ValueError('Transmitted sender name/text unavailable; retries disabled.')
    # Firmware truncates the sender-prefixed group text at MAX_TEXT_LEN=160.
    text=(name+': '+message).encode('utf-8')[:160]
    payload=5+len(text) # 4-byte timestamp and one text-type byte.
    size=2+(4 if scoped else 0)+3+16*math.ceil(payload/16) # header/path, scope, channel hash/MAC, ciphertext.
    symbol=(2**sf)/(bw*1000)
    ldro=int(symbol>=.016)
    bits=max(0,8*size+16-4*sf+(0 if sf<=6 else 8)+20)
    symbols=math.ceil(bits/(4*(sf-2*ldro)))*cr
    airtime=((32 if sf<=8 else 16)+8+(6.25 if sf<=6 else 4.25)+symbols)*symbol
    if not 0<airtime<=MAX_PACKET_AIRTIME:
        raise ValueError('Estimated packet airtime exceeds the retry safety limit.')
    # Firmware getEstAirtimeFor truncates to milliseconds; client adds 1.2.
    return {'packet_bytes':size,'airtime':airtime,'timeout':(500+16*int(airtime*1000))/1000*1.2}


def retry_delay(protocol_timeout,hops):
    """A fresh jitter draw per wait; unknown hops never schedule retries."""
    if type(hops) is not int or not 0<=hops<=63:return None
    return max(protocol_timeout,20.0 if hops==0 else 30.0)+random.uniform(0.0,5.0)


@dataclass
class Job:
    root:int
    command:int
    channel:int
    message:str
    scope:str
    scope_key:bytes|None
    channel_key:bytes
    hops:int
    stamp:int
    info:dict
    timing:dict
    stop:asyncio.Event=field(default_factory=asyncio.Event)
    reason:str=''
    task:object=None


class ReplyRetries:
    def __init__(self,companion):
        self.c=companion
        self.jobs={}
        self.closed=False
        self.budget=deque()
        self.clock=time.monotonic
        self.wait=self._wait
        # Pending work is deliberately not resumed after a restart.
        reply_store.interrupt_pending(self.c.database.db)

    async def _wait(self,job,seconds):
        try:await asyncio.wait_for(job.stop.wait(),seconds)
        except asyncio.TimeoutError:pass

    def state(self,root,status,detail='',next_at=None):
        reply_store.retry_state(self.c.database.db,root,status,detail,next_at)

    def connected(self):
        return getattr(getattr(self.c.mc,'connection_manager',None),'is_connected',False) is True

    def context(self,job):
        return (not self.closed and self.connected() and self.c.channel_idx==job.channel and self.c.tracking_key==job.channel_key
                and self.c.room_bot_id is None and not job.stop.is_set())

    def schedule(self,root,command,channel,message,scope,scope_key,stamp,hops):
        maximum=2 if type(hops) is int and hops==0 else 4 if type(hops) is int and 1<=hops<=63 else 1
        reply_store.retry_plan(self.c.database.db,root,hops,maximum)
        if maximum==1:
            self.state(root,'not scheduled','Unknown incoming hop count; original submission only.');return
        try:
            if self.closed:raise ValueError('Radio session is closing; retries disabled.')
            if not self.connected():raise ValueError('Companion disconnected; retries disabled.')
            info=dict(self.c.mc.self_info)
            values=timing(info,message,scope_key is not None)
            if not info.get('public_key'):raise ValueError('Companion identity unavailable; retries disabled.')
            if len(self.jobs)>=MAX_PENDING:raise ValueError('Pending reply safety limit reached.')
        except (ValueError,TypeError,AttributeError) as exc:
            self.state(root,'not scheduled',str(exc));return
        job=Job(root,command,channel,message,scope,scope_key,self.c.tracking_key,hops,stamp,info,values)
        self.jobs[root]=job
        self.state(root,'pending','Retry scheduled; waiting to start timer.')
        job.task=asyncio.create_task(self.run(job,maximum),name='reply-retry-'+str(root))

    def evidence(self,reply_id):
        root=reply_store.root_id(self.c.database.db,reply_id)
        job=self.jobs.get(root)
        if job and job.hops>0:
            job.reason='Matching forwarding observed; receiver delivery remains unconfirmed.'
            job.stop.set()
            self.state(root,'forwarding observed',job.reason)

    def cancel(self,reason):
        for job in tuple(self.jobs.values()):
            job.reason=reason;job.stop.set()
            self.state(job.root,'cancelled',reason)

    async def close(self):
        self.closed=True
        self.cancel('Session ended; pending retries cancelled.')
        tasks=[j.task for j in self.jobs.values()]
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        self.jobs.clear()

    def has_evidence(self,job):
        return job.hops>0 and reply_store.has_forwarding(self.c.database.db,job.root)

    async def run(self,job,maximum):
        def stopped():
            if self.has_evidence(job):
                job.reason='Matching forwarding observed; receiver delivery remains unconfirmed.';job.stop.set()
            if not self.context(job):
                self.state(job.root,'forwarding observed' if self.has_evidence(job) else 'cancelled',job.reason or 'Companion connection or channel changed.');return True
            return False
        try:
            deferrals=0;attempt=2
            while attempt<=maximum:
                if stopped():return
                delay=retry_delay(job.timing['timeout'],job.hops)
                self.state(job.root,'pending',f'Waiting {delay:.1f}s: protocol timeout with hop minimum and jitter.',time.time()+delay)
                await self.wait(job,delay)
                if stopped():return
                # Same lock order as incoming channel handlers and control writes.
                async with self.c.control_lock:
                    if stopped():return
                    info=await self.c.get_self_info()
                    if not isinstance(info,dict) or any(info.get(k)!=job.info.get(k) for k in RADIO_FIELDS):
                        self.state(job.root,'cancelled','Companion identity, name or radio settings changed.');return
                    result=await self.c.mc.commands.get_stats_core()
                    queue=(result.payload or {}).get('queue_len') if result and result.type==EventType.STATS_CORE else None
                    if type(queue) is not int or queue!=0:
                        deferrals+=1
                        if deferrals>=3:
                            self.state(job.root,'cancelled','Transmit queue busy or unavailable after bounded deferrals.');return
                        continue
                    if stopped():return
                    now=self.clock()
                    while self.budget and now-self.budget[0][0]>=3600:self.budget.popleft()
                    if sum(v for _,v in self.budget)+job.timing['airtime']>MAX_RETRY_AIRTIME:
                        self.state(job.root,'cancelled','Additional retry airtime budget reached.');return
                    # Distinct per-part timestamp even if the host clock steps back.
                    job.stamp=max(int(time.time()),job.stamp+1,self.c._reply_timestamp+1)
                    if job.stamp>0xffffffff:
                        self.state(job.root,'cancelled','Packet timestamp out of range.');return
                    self.budget.append((now,job.timing['airtime']))
                    _,rid=await self.c._transmit_reply(job.channel,job.message,job.scope,job.scope_key,job.command,
                                                     stamp=job.stamp,parent=job.root,attempt=attempt)
                    if rid is None:
                        self.state(job.root,'cancelled','Attempt tracking unavailable; further retransmission stopped.');return
                    attempt+=1;deferrals=0
            if not stopped():self.state(job.root,'exhausted','Attempt limit reached; receiver delivery remains unconfirmed.')
        except asyncio.CancelledError:
            self.state(job.root,'cancelled',job.reason or 'Retry task cancelled.');raise
        except Exception as exc:
            self.c.logger.warning('Reply retry stopped: %s',exc)
            self.state(job.root,'cancelled','Retry stopped: '+type(exc).__name__)
        finally:self.jobs.pop(job.root,None)
