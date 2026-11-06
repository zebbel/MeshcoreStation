"""Bounded firmware snapshots inside the existing opt-in neighbor scheduler."""
import asyncio
import time
from meshcorestation.radio import averaged_snr as wire
from meshcorestation.storage import averaged_snr as store

MAX_RECORDS=32
CYCLE_SECONDS=180
PROBE_INTERVAL=6*3600


class PartialCollection(ValueError):pass
class RemoteStatus(wire.ProtocolError):
    def __init__(self,status):
        self.status=status
        super().__init__('Repeater boot session changed; a fresh snapshot will start next poll.' if status==3 else 'Averaged-SNR status: '+wire.STATUS[status].replace('_',' '))


async def collect(monitor,companion,cfg,contact,login,poll_id):
    path=monitor.path
    await asyncio.to_thread(store.recover_collection,path,cfg['public_key'])
    cached=await asyncio.to_thread(store.status,path,cfg['public_key'])
    firmware=login.get('fw_ver_level') if isinstance(login,dict) else None
    if type(firmware) is not int:firmware=None
    changed=cached['firmware_level'] is not None and cached['firmware_level']!=firmware
    known=cached['capability']=='averaged'
    rechecking=changed or cached['detection']=='recheck_requested' or cached['probe_after']<=time.time()
    if not known and not rechecking:return False
    if not callable(getattr(companion.mc.commands,'send_binary_req',None)):
        await asyncio.to_thread(store.update,path,cfg,detection='client_transport_unavailable',probe_after=time.time()+PROBE_INTERVAL,
            error='Generic binary transport unavailable; legacy monitoring retained.')
        return False
    started=time.time();mono=time.monotonic();deadline=mono+CYCLE_SECONDS
    records=0;complete=False;validated=False;gaps_seen=False;warning='';failure=''
    session=cached['session'];ceiling=cached['ceiling'];cursor=cached['cursor'];seen=cached['seen_sequence'];last_window=cached['last_window']
    def warn(text):
        nonlocal warning
        if text not in warning:warning=(warning+' '+text).strip()[:1000]
    async def update(**values):
        if not await asyncio.to_thread(store.update,path,cfg,**values):raise ValueError('Monitoring changed; SNR continuation cancelled.')
    async def page(boot,limit,after,count):
        payload=wire.request(boot,limit,after,count)
        raw=await monitor.exchange(companion,cfg,lambda:wire.exchange(companion,contact,payload))
        return raw,wire.decode(raw,session=boot,ceiling=limit,cursor=after,requested_count=count)
    async def save(h,raw,gap=None):
        nonlocal gaps_seen
        if not await asyncio.to_thread(store.record,path,cfg,poll_id,started,h,raw,warning,gap):raise ValueError('Monitoring changed; SNR evidence not committed.')
        if gap and gap[0]<=gap[1]:gaps_seen=True
    def checked(h):
        if h['status']:raise RemoteStatus(h['status'])
    def diagnostics(h):return {k:v for k,v in h.items() if k!='record'}
    def losses(h):
        if any(h[k] for k in ('expired','evicted','dropped')):
            warn('Firmware reports cumulative expiry, eviction or drop counters; some records may already be saved locally. These are boot totals, not losses attributed to this poll.')
        if cached['session']==h['session'] and any(h[k]<cached['diagnostics'].get(k,0) for k in ('expired','evicted','dropped')):
            warn('Firmware diagnostics decreased within one session; history consistency is uncertain.')
    if cfg['interval_minutes']>=120:warn('Configured interval approaches or exceeds two-hour firmware retention; windows may expire before collection.')
    try:
        if not cached['pending']:
            raw,h=await page(wire.ZERO_SESSION,0,0,0);checked(h);validated=True
            if session and session!=h['session']:
                warn('Repeater boot session changed; records from different boots remain separate.');seen=0
            session=h['session'];ceiling=h['ceiling'];cursor=seen
            if cursor>ceiling:raise wire.ProtocolError('SNR sequence regressed within one boot session.')
            losses(h)
            if min(h['retained'],ceiling-cursor)>MAX_RECORDS:warn('Snapshot may require several configured polls; monitor two-hour retention risk.')
            gap=(cursor+1,h['oldest']-1) if h['oldest']>cursor+1 else None
            if gap:warn('Missing retained sequence range; not proof that every absent record was lost during this poll.')
            await save(h,raw,gap)
            await update(capability='averaged',detection='supported',firmware_level=firmware,probe_after=time.time()+PROBE_INTERVAL,
                session=session,ceiling=ceiling,cursor=cursor,seen_sequence=seen,pending=int(cursor<ceiling),diagnostics=diagnostics(h),error='')
            complete=cursor==ceiling
        for _ in range(MAX_RECORDS):
            if complete:break
            if time.monotonic()+40>deadline:
                warn('Per-cycle time budget reached; the fixed snapshot continuation is saved.');break
            raw,h=await page(session,ceiling,cursor,1);checked(h);validated=True;losses(h)
            item=h['record'];gap=None
            if item and item['sequence']>cursor+1:gap=(cursor+1,item['sequence']-1)
            if not h['more'] and not item and cursor<ceiling:gap=(cursor+1,ceiling)
            if gap:warn('Missing retained sequence range; origin and timing of loss are uncertain.')
            if item and not item['utc_start']:warn('Records without valid UTC are preserved without assigning historical dates.')
            if item and item['flags']&2:warn('Firmware reports a clock discontinuity.')
            if item and item['flags']&4:warn('Sample-count overflow makes this window incomplete.')
            await save(h,raw,gap);cursor=h['cursor'];records+=int(item is not None);complete=not h['more']
            if complete and cursor<ceiling:
                if item:
                    warn('Snapshot tail is no longer retained; missing sequences were recorded.')
                    await save(dict(h,record=None),raw,(cursor+1,ceiling))
                cursor=ceiling
            if item and item['utc_end']:last_window=max(last_window or 0,item['utc_end'])
            # seen_sequence is a scan watermark, not evidence of receptions:
            # absent sequences have their own durable gap records.
            await update(session=session,ceiling=ceiling,cursor=cursor,seen_sequence=max(seen,cursor),pending=int(not complete),last_window=last_window,diagnostics=diagnostics(h))
        if not complete:warn('Collection partial: continuation saved for the next configured poll. Large neighbor populations may exceed two-hour retention; review the configured interval.')
        await update(last_collection=time.time(),records_retrieved=records,completeness='complete_with_gaps' if complete and gaps_seen else 'complete_with_warnings' if complete and warning else 'complete' if complete else 'partial',warning=warning,error='')
        if not complete:raise PartialCollection('Aggregate cycle budget reached; continuation saved, collection incomplete.')
        return True
    except PartialCollection:
        failure='Aggregate collection partial; continuation saved for the next configured interval.';raise
    except asyncio.CancelledError:
        failure='Aggregate collection interrupted; validated records and continuation are preserved.'
        await asyncio.to_thread(store.update,path,cfg,completeness='partial' if records else 'interrupted',records_retrieved=records,last_collection=time.time() if records else cached['last_collection'],error=failure,warning=warning)
        raise
    except (asyncio.TimeoutError,wire.ProtocolError) as exc:
        failure='Averaged-SNR request timed out; capability remains unconfirmed.' if isinstance(exc,asyncio.TimeoutError) else str(exc)
        if isinstance(exc,RemoteStatus) and exc.status==3:
            await update(capability='averaged',detection='session_changed',pending=0,session='',cursor=0,ceiling=0,seen_sequence=0,probe_after=0,
                completeness='partial' if records else 'interrupted',records_retrieved=records,error=failure,warning=warning)
            raise
        if isinstance(exc,RemoteStatus) and exc.status in (1,4,5):
            await update(capability='legacy' if exc.status==1 else 'averaged',detection=wire.STATUS[exc.status],probe_after=time.time()+PROBE_INTERVAL,
                completeness='partial' if records else 'unavailable',records_retrieved=records,error=failure,warning=warning)
            return False
        fallback=not validated and (not known or rechecking)
        await update(capability='unknown' if fallback else 'averaged' if validated else cached['capability'],
            detection='unreachable' if isinstance(exc,asyncio.TimeoutError) else 'unknown_version' if isinstance(exc,wire.UnsupportedVersion) else 'protocol_error',
            probe_after=time.time()+PROBE_INTERVAL if fallback else cached['probe_after'],completeness='partial' if records else 'unavailable',
            records_retrieved=records,last_collection=time.time() if records else cached['last_collection'],error=failure,warning=warning)
        if fallback:return False # a failed probe is not a permanent unsupported classification
        raise
    except Exception as exc:
        failure=str(exc) or type(exc).__name__
        await update(completeness='partial' if records else 'unavailable',records_retrieved=records,error=failure,warning=warning)
        raise
    finally:
        await asyncio.to_thread(store.update,path,cfg,duration_seconds=max(0,time.monotonic()-mono))
        await asyncio.to_thread(store.finish_for,path,cfg['public_key'],poll_id,complete,failure,warning)
