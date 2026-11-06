"""Hardware-independent 0x70/v1 codec and standard Companion binary transport.

Reference: zebbel/MeshCore meshcoreStation-v1.0.20/docs/xiao-neighbour-snr.md.
The client's generic BINARY_RESPONSE has already removed the echoed request tag.
"""
import asyncio
from enum import Enum
import struct
from meshcore import EventType

VERSION=1
HEADER=struct.Struct('<BBBB16s7I4H2I')
RECORD=struct.Struct('<32s6IqIbbBBI')
ZERO_SESSION='00'*16
STATUS={1:'unsupported_version',2:'invalid_request',3:'session_changed',4:'response_capacity',5:'session_entropy_unavailable'}


class ProtocolError(ValueError):pass
class UnsupportedVersion(ProtocolError):pass


class RequestType(Enum):
    AVERAGED_NEIGHBORS=0x70


def request(session=ZERO_SESSION,ceiling=0,cursor=0,count=1):
    try:boot=bytes.fromhex(session)
    except (TypeError,ValueError):raise ProtocolError('Invalid SNR boot session.') from None
    if len(boot)!=16 or type(count) is not int or count not in (0,1) or any(type(v) is not int or not 0<=v<=0xffffffff for v in (ceiling,cursor)):
        raise ProtocolError('Invalid SNR snapshot parameters.')
    if cursor>ceiling or (not any(boot) and (ceiling or cursor)):raise ProtocolError('Invalid SNR snapshot cursor.')
    return struct.pack('<BBBB16sII',0x70,VERSION,count,0,boot,ceiling,cursor)


def decode(raw,*,session=ZERO_SESSION,ceiling=0,cursor=0,requested_count=1):
    request(session,ceiling,cursor,requested_count)
    if not isinstance(raw,bytes) or not 64<=len(raw)<=180:raise ProtocolError('Truncated or oversized averaged-SNR response.')
    version,status,count,more,boot,limit,after,oldest,newest,expired,evicted,dropped,active,retained,capacity,identities,old_window,new_window=HEADER.unpack_from(raw)
    if version!=VERSION:raise UnsupportedVersion('Unknown averaged-SNR version; measurements were not decoded.')
    if status not in (0,*STATUS) or count not in (0,1) or more not in (0,1):raise ProtocolError('Invalid SNR response flags.')
    needed=64+(76 if not status and count else 0)
    if len(raw)<needed or len(raw)>needed+15 or (status and (count or more)):raise ProtocolError('Invalid SNR record length or error status.')
    h=dict(version=version,status=status,session=boot.hex(),ceiling=limit,cursor=after,more=bool(more),oldest=oldest,newest=newest,
        expired=expired,evicted=evicted,dropped=dropped,active=active,retained=retained,capacity=capacity,identities=identities,
        oldest_window=old_window,newest_window=new_window,record=None)
    if status:return h
    if not any(boot) or not capacity or not identities or active>identities or retained>capacity or oldest>newest or bool(oldest)!=bool(newest):
        raise ProtocolError('Invalid SNR diagnostics or boot identity.')
    if (not retained and (oldest or newest)) or (retained and (not oldest or retained>newest-oldest+1)) or old_window>new_window:
        raise ProtocolError('Inconsistent retained SNR sequence range.')
    if session!=ZERO_SESSION and (boot.hex()!=session or limit!=ceiling):raise ProtocolError('SNR snapshot session or ceiling changed unexpectedly.')
    if after>limit or after<cursor or (more and not count and requested_count!=0) or (not count and after!=cursor) or count>requested_count:
        raise ProtocolError('SNR pagination made no valid progress.')
    if count:
        key,seq,window,start,end,utc_start,utc_end,total,samples,minimum,maximum,flags,reserved,last=RECORD.unpack_from(raw,64)
        if not any(key) or seq<=cursor or seq!=after or seq>limit or not oldest<=seq<=newest:raise ProtocolError('Invalid SNR record identity or sequence.')
        if end-start!=1800 or start!=window*1800 or not start<=last<end or not samples or minimum>maximum or not minimum*samples<=total<=maximum*samples or reserved or flags&~7:
            raise ProtocolError('Invalid SNR aggregate measurement.')
        valid=bool(flags&1)
        if valid and (flags&2 or not 1577836800<=utc_start<4102444800 or utc_end-utc_start!=1800):raise ProtocolError('Invalid UTC-valid SNR window.')
        if not valid and (utc_start or utc_end):raise ProtocolError('Invalid SNR clock flags/timestamps.')
        h['record']=dict(neighbor_key=key.hex(),sequence=seq,window=window,mono_start=start,mono_end=end,utc_start=utc_start if valid else None,
            utc_end=utc_end if valid else None,snr_sum=total,sample_count=samples,minimum=minimum,maximum=maximum,flags=flags,last_mono=last,
            last_utc=utc_start+last-start if valid else None)
    return h


async def exchange(companion,contact,payload,timeout=30):
    """One authenticated full-key request. Subscribe before send to capture early replies.

    Generic pushes have no sender field. The Companion validates encrypted replies;
    the request's echoed tag binds them to the selected authenticated contact.
    The caller owns the shared control lock; the client binary lock is also used.
    """
    if not isinstance(payload,bytes) or len(payload)!=28 or payload[0]!=0x70:raise ProtocolError('Invalid SNR request.')
    _,version,count,reserved,boot,ceiling,cursor=struct.unpack('<BBBB16sII',payload)
    if version!=VERSION or reserved or payload!=request(boot.hex(),ceiling,cursor,count):raise ProtocolError('Invalid SNR request parameters.')
    commands=companion.mc.commands
    if not callable(getattr(commands,'send_binary_req',None)):raise ProtocolError('Generic binary transport unavailable.')
    expected=None;early=[];future=asyncio.get_running_loop().create_future()
    def accept(data):
        tag=data.get('tag');tag=tag.hex() if isinstance(tag,bytes) else tag
        if tag!=expected or future.done():return
        prefix=data.get('pubkey_prefix')
        if prefix is not None and str(prefix).lower()!=contact['public_key'][:12]:return
        try:
            raw=data.get('data')
            if not isinstance(raw,str) or len(raw)>360:raise ValueError()
            raw=bytes.fromhex(raw)
        except (TypeError,ValueError):future.set_exception(ProtocolError('Malformed binary SNR response.'));return
        future.set_result(raw)
    async def receive(event):
        data=event.payload
        if not isinstance(data,dict):return
        if expected is None:
            if len(early)<16:
                raw=data.get('data')
                early.append(dict(tag=data.get('tag'),pubkey_prefix=data.get('pubkey_prefix'),data=raw if isinstance(raw,str) and len(raw)<=360 else None))
        else:accept(data)
    reader=getattr(commands,'_reader',None)
    lock=getattr(commands,'_mesh_request_lock',None) or asyncio.Lock()
    async with lock:
        before=set(reader.pending_binary_requests) if reader is not None else set()
        subscription=companion.mc.subscribe(EventType.BINARY_RESPONSE,receive)
        try:
            result=await asyncio.wait_for(commands.send_binary_req(contact,RequestType.AVERAGED_NEIGHBORS,data=payload[1:],timeout=timeout),timeout)
            if result is None or result.type!=EventType.MSG_SENT or not isinstance(result.payload,dict):raise ProtocolError('Companion did not accept the binary SNR request.')
            tag=result.payload.get('expected_ack')
            if not isinstance(tag,bytes) or len(tag)!=4:raise ProtocolError('Invalid binary request tag.')
            expected=tag.hex()
            for data in early:accept(data)
            return await asyncio.wait_for(future,timeout)
        finally:
            subscription.unsubscribe()
            if not future.done():future.cancel()
            if reader is not None:
                for tag,info in list(reader.pending_binary_requests.items()):
                    if tag not in before and info.get('request_type')==RequestType.AVERAGED_NEIGHBORS and info.get('pubkey_prefix')==contact['public_key'][:12]:
                        reader.pending_binary_requests.pop(tag,None)
