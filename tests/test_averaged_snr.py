"""Firmware-generated vectors and fake standard serial transport, never RF."""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
import time
from types import SimpleNamespace as NS,MethodType
from unittest.mock import Mock,AsyncMock
import pytest
from meshcore import EventType
from meshcore.commands.base import CommandHandlerBase
from meshcorestation import config
from meshcorestation.radio import averaged_snr as wire,averaged_snr_collection as collection,neighbor_monitor as monitor
from meshcorestation.storage import database,voltage_store,neighbor_snr as legacy,averaged_snr as store,passive_stats
from meshcorestation.storage.connection import connect
from meshcorestation.storage.statistics_view import aggregate
from test_neighbor_monitor import station,A,B,C
from fake_companion import FakeMeshCore,event

BOOT='01'+'00'*15;UTC=1700000000
VECTORS=json.loads((Path(__file__).parent/'fixtures/averaged_snr_v1.json').read_text())


def response(seq=1,window=0,count=2,total=-7,session=BOOT,key=B,more=False,ceiling=None,flags=1,utc=None,minimum=-13,maximum=6):
    start=window*1800;utc=UTC+start if utc is None else utc
    return wire.HEADER.pack(1,0,1,int(more),bytes.fromhex(session),ceiling or seq,seq,1,ceiling or seq,0,0,0,1,ceiling or seq,400,100,0,window)+wire.RECORD.pack(
        bytes.fromhex(key),seq,window,start,start+1800,utc if flags&1 else 0,utc+1800 if flags&1 else 0,total,count,minimum,maximum,flags,0,start)


def header_for(rows,session=BOOT,cursor=0,ceiling=None,diagnostics=False,expired=0):
    ids=[wire.HEADER.unpack_from(r)[6] for r in rows]
    ceiling=max(ids,default=0) if ceiling is None else ceiling
    available=[r for r in rows if cursor<wire.HEADER.unpack_from(r)[6]<=ceiling]
    record=available[0][64:140] if available and not diagnostics else b''
    after=wire.RECORD.unpack(record)[1] if record else cursor
    return wire.HEADER.pack(1,0,int(bool(record)),int(any(wire.HEADER.unpack_from(r)[6]>after for r in available)),bytes.fromhex(session),ceiling,after,
        min(ids,default=0),max(ids,default=0),expired,0,0,1,len(rows),400,100,0,10)+record


def cfg():return legacy.save_settings(database.DB_FILE,A,True,30)
def make_due(key=A):
    with closing(connect(database.DB_FILE)) as db,db:db.execute('UPDATE neighbor_monitor SET next_due=0 WHERE public_key=?',(key,))
    return legacy.settings(database.DB_FILE,key)
def record(configuration,raw,poll='one'):
    h=wire.decode(raw);assert store.record(database.DB_FILE,configuration,poll,UTC,h,raw)
    store.finish_for(database.DB_FILE,A,poll,True);return h


def test_firmware_vectors_and_exact_signed_values():
    h=wire.decode(bytes.fromhex(VECTORS['example']))
    assert wire.request().hex()=='70010100'+'00'*24
    assert (wire.HEADER.size,wire.RECORD.size)==(64,76)
    r=h['record'];assert (r['snr_sum'],r['sample_count'],r['minimum'],r['maximum'])==(-7,2,-13,6)
    assert r['snr_sum']/(4*r['sample_count'])==-.875
    assert wire.decode(bytes.fromhex(VECTORS['diagnostics']),requested_count=0)['more']
    assert wire.decode(bytes.fromhex(VECTORS['empty_continuation']),session=BOOT,ceiling=1,cursor=1)['record'] is None
    assert wire.decode(bytes.fromhex(VECTORS['unsupported_version']))['status']==1
    assert wire.decode(bytes.fromhex(VECTORS['session_changed']))['status']==3
    r=wire.decode(bytes.fromhex(VECTORS['invalid_utc']))['record'];assert r['utc_start'] is None and r['last_utc'] is None
    r=wire.decode(response(count=0xffffffff,total=-128*0xffffffff,minimum=-128,maximum=-128))['record']
    assert r['snr_sum']==-549755813760 and r['sample_count']==4294967295


@pytest.mark.parametrize('offset,value',[(0,2),(1,99),(2,2),(3,2),(132,7),(134,8),(135,1)])
def test_invalid_protocol_fields(offset,value):
    raw=bytearray(response());raw[offset]=value
    with pytest.raises(wire.ProtocolError):wire.decode(bytes(raw))


@pytest.mark.parametrize('length',[0,1,63,64,100,139,181])
def test_bad_lengths(length):
    raw=response();raw=raw[:length] if length<=len(raw) else raw+b'\0'*(length-len(raw))
    with pytest.raises(wire.ProtocolError):wire.decode(raw)


def test_snapshot_validation_and_empty_fixed_snapshot():
    with pytest.raises(wire.ProtocolError):wire.request(BOOT,1,2)
    with pytest.raises(wire.ProtocolError):wire.request(wire.ZERO_SESSION,1,0)
    with pytest.raises(wire.ProtocolError):wire.decode(response(),session='02'+'00'*15,ceiling=1)
    with pytest.raises(wire.ProtocolError):wire.decode(response(),session=BOOT,ceiling=2)
    empty=wire.HEADER.pack(1,0,0,0,bytes.fromhex(BOOT),0,0,0,0,0,0,0,0,0,200,50,0,0)
    assert wire.decode(empty,session=BOOT)['ceiling']==0
    assert wire.decode(bytes.fromhex(VECTORS['unsupported_version'])+b'\0'*8)['status']==1


def transport_fixture(handler):
    mc=FakeMeshCore();mc.contacts={A:dict(public_key=A,type=2,adv_name='Managed')}
    commands=mc.commands;commands._reader=None;commands._mesh_request_lock=asyncio.Lock()
    commands.send_binary_req=MethodType(CommandHandlerBase.send_binary_req,commands)
    companion=NS(mc=mc,control_lock=asyncio.Lock());calls=[];legacy_calls=[]
    async def send(payload,events):
        assert companion.control_lock.locked();calls.append(payload)
        assert payload[:33]==b'\x32'+bytes.fromhex(A) and len(payload)==61
        answer=await handler(payload[33:])
        if isinstance(answer,Exception):raise answer
        if answer is not None:
            for callback in list(mc.subscriptions.get(EventType.BINARY_RESPONSE,[])):
                await callback(event(EventType.BINARY_RESPONSE,tag='ffffffff',data=answer.hex()))
                await callback(event(EventType.BINARY_RESPONSE,tag='12345678',data=answer.hex(),pubkey_prefix=C[:12]))
                await callback(event(EventType.BINARY_RESPONSE,tag='12345678',data=answer.hex()))
        return event(EventType.MSG_SENT,expected_ack=bytes.fromhex('12345678'))
    commands.send=send
    async def login(contact,password,**kw):
        assert password=='' and companion.control_lock.locked()
        return event(EventType.LOGIN_SUCCESS,pubkey_prefix=contact['public_key'][:12],is_admin=False,fw_ver_level=8)
    commands.send_login_sync=login
    async def neighbors(contact,**kw):
        assert companion.control_lock.locked();legacy_calls.append(contact['public_key'])
        return dict(pubkey_prefix=contact['public_key'][:12],neighbours=[dict(pubkey=B[:8],snr=3,secs_ago=5)],neighbours_count=1,results_count=1)
    commands.req_neighbours_sync=neighbors
    return companion,calls,legacy_calls


def monitor_fixture(monkeypatch,handler):
    companion,calls,old=transport_fixture(handler)
    worker=monitor.NeighborMonitor(NS(companion=companion,control=object(),logger=Mock()),database.DB_FILE)
    monkeypatch.setattr(monitor,'REQUEST_GAP',0);original=wire.exchange
    async def quick(*args,**kw):return await original(*args,timeout=.02)
    monkeypatch.setattr(wire,'exchange',quick)
    return worker,calls,old


def handler_for(rows,state=None):
    state=state or dict(session=BOOT,expired=0)
    async def handle(payload):
        typ,version,count,reserved,boot,ceiling,cursor=struct.unpack('<BBBB16sII',payload)
        assert (typ,version,reserved)==(0x70,1,0)
        if any(boot) and boot.hex()!=state['session']:
            return wire.HEADER.pack(1,3,0,0,bytes.fromhex(state['session']),ceiling,cursor,0,0,0,0,0,0,0,400,100,0,0)
        return header_for(rows,session=state['session'],cursor=cursor,ceiling=ceiling if any(boot) else None,diagnostics=count==0,expired=state['expired'])
    return handle


def test_actual_client_frame_early_tag_matching_and_cleanup():
    async def run():
        async def handle(payload):assert payload==wire.request();return response()
        companion,calls,_=transport_fixture(handle)
        async with companion.control_lock:r=await wire.exchange(companion,companion.mc.contacts[A],wire.request(),timeout=.1)
        assert wire.decode(r)['record']['snr_sum']==-7 and len(calls)==1
        assert not companion.mc.subscriptions[EventType.BINARY_RESPONSE]
    asyncio.run(run())


def test_transport_timeout_no_retry_and_cleanup():
    async def run():
        async def handle(payload):return None
        companion,calls,_=transport_fixture(handle)
        async with companion.control_lock:
            with pytest.raises(asyncio.TimeoutError):await wire.exchange(companion,companion.mc.contacts[A],wire.request(),timeout=.01)
        assert len(calls)==1 and not companion.mc.subscriptions[EventType.BINARY_RESPONSE]
    asyncio.run(run())


def test_storage_dedup_weighting_and_legacy_preservation(station):
    c=cfg();record(c,response());record(c,response(),'repeated');record(c,response(seq=2,window=1,count=10,total=20),'two')
    record(c,response(session='02'+'00'*15,window=2),'other-boot')
    path=passive_stats.statistics_path(database.DB_FILE,A)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM neighbor_snr_aggregates').fetchone()[0]==3
        assert db.execute('SELECT average_snr FROM neighbor_snr_aggregates WHERE sequence=2').fetchone()[0]==.5
        assert db.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
    with pytest.raises(ValueError,match='Conflicting'):record(c,response(total=-6),'conflict')
    legacy.record_page(database.DB_FILE,c,'legacy',UTC+100,UTC+102,[dict(pubkey=B[:8],snr=20,secs_ago=5)])
    for days in (1,7,30):
        r=aggregate(database.DB_FILE,A,days,now=UTC+3600)['neighbor_snr'][0]
        assert r['public_key']==B and r['source']=='firmware_aggregates' and r['samples']==12
        assert r['average_snr']==pytest.approx(13/48) and r['minimum_snr']==-3.25 and r['maximum_snr']==1.5
    with closing(sqlite3.connect(path)) as db:assert db.execute('SELECT COUNT(*) FROM neighbor_snr_measurements').fetchone()[0]==1
    station.create_database();assert store.status(database.DB_FILE,A)['capability']=='unknown'


def test_utc_discontinuities_boundary_and_unknown_full_key(station):
    c=cfg();record(c,response(flags=2));record(c,response(seq=2,window=1,key='dd'*32),'unknown')
    view=aggregate(database.DB_FILE,A,1,now=UTC+3601)
    assert len(view['neighbor_snr'])==1 and view['neighbor_snr'][0]['public_key']=='dd'*32
    assert view['neighbor_snr'][0]['name'] is None and view['neighbor_snr'][0]['resolution']=='matched'
    assert view['neighbor_snr_quality']['invalid_utc_records']==1 and view['neighbor_snr_quality']['discontinuous_records']==1
    short=aggregate(database.DB_FILE,A,1,now=UTC+2700)
    assert not short['neighbor_snr'] and short['neighbor_snr_quality']['boundary_windows']==1


def test_continuation_budgets_and_restart(station,monkeypatch):
    async def run():
        cfg();rows=[response(seq=i,window=i-1,count=i,total=i,ceiling=3) for i in (1,2,3)]
        worker,calls,old=monitor_fixture(monkeypatch,handler_for(rows));monkeypatch.setattr(collection,'MAX_RECORDS',1)
        await worker.tick();p=store.status(database.DB_FILE,A)
        assert p['pending'] and p['cursor']==1 and p['completeness']=='partial' and len(calls)==2
        make_due();worker=monitor.NeighborMonitor(worker.runtime,database.DB_FILE);await worker.tick()
        assert store.status(database.DB_FILE,A)['cursor']==2 and len(calls)==3
        make_due();await worker.tick();p=store.status(database.DB_FILE,A)
        assert not p['pending'] and p['cursor']==3 and p['capability']=='averaged' and not old
        with closing(sqlite3.connect(passive_stats.statistics_path(database.DB_FILE,A))) as db:assert db.execute('SELECT COUNT(*) FROM neighbor_snr_aggregates').fetchone()[0]==3
    asyncio.run(run())


@pytest.mark.parametrize('mode',['timeout','malformed','unsupported','future'])
def test_probe_failures_preserve_legacy_and_recheck(station,monkeypatch,mode):
    async def run():
        cfg()
        async def handle(payload):return {'timeout':None,'malformed':b'bad','unsupported':bytes.fromhex(VECTORS['unsupported_version']),'future':b'\x02'+response()[1:]}[mode]
        worker,calls,old=monitor_fixture(monkeypatch,handle);await worker.tick();p=store.status(database.DB_FILE,A)
        assert old==[A] and p['capability']==('legacy' if mode=='unsupported' else 'unknown')
        assert p['detection']==dict(timeout='unreachable',malformed='protocol_error',unsupported='unsupported_version',future='unknown_version')[mode]
        make_due();await worker.tick();assert len(calls)==1 and len(old)==2
        before=legacy.settings(database.DB_FILE,A);store.recheck(database.DB_FILE,A);assert legacy.settings(database.DB_FILE,A)==before
        make_due();await worker.tick();assert len(calls)==2
    asyncio.run(run())


def test_reboots_and_retention_gaps(station,monkeypatch):
    async def run():
        cfg();rows=[response(seq=i,window=i-1,ceiling=3) for i in (1,2,3)];state=dict(session=BOOT,expired=0)
        worker,_,_=monitor_fixture(monkeypatch,handler_for(rows,state));monkeypatch.setattr(collection,'MAX_RECORDS',1)
        await worker.tick();rows[:]=[rows[-1]];state['expired']=2;make_due();await worker.tick()
        p=store.status(database.DB_FILE,A);assert p['completeness']=='complete_with_gaps' and not p['pending']
        with closing(sqlite3.connect(passive_stats.statistics_path(database.DB_FILE,A))) as db:
            assert db.execute('SELECT first_sequence,last_sequence FROM neighbor_snr_sequence_gaps').fetchall()==[(2,2)]
            assert db.execute('SELECT SUM(sample_count) FROM neighbor_snr_aggregates').fetchone()[0]==4
        state['session']='02'+'00'*15;rows[:]=[response(session=state['session'])];make_due();await worker.tick()
        with closing(sqlite3.connect(passive_stats.statistics_path(database.DB_FILE,A))) as db:assert db.execute('SELECT COUNT(DISTINCT session) FROM neighbor_snr_aggregates').fetchone()[0]==2
    asyncio.run(run())


def test_session_mismatch_in_pending_snapshot(station,monkeypatch):
    async def run():
        cfg();rows=[response(seq=i,window=i-1,ceiling=2) for i in (1,2)];state=dict(session=BOOT,expired=0)
        worker,_,_=monitor_fixture(monkeypatch,handler_for(rows,state));monkeypatch.setattr(collection,'MAX_RECORDS',1)
        await worker.tick();state['session']='02'+'00'*15;make_due();await worker.tick()
        assert store.status(database.DB_FILE,A)['pending']==0 and store.status(database.DB_FILE,A)['detection']=='session_changed'
    asyncio.run(run())


def test_page_failure_retains_records_and_continuation(station,monkeypatch):
    async def run():
        cfg();normal=handler_for([response(seq=i,window=i-1,ceiling=2) for i in (1,2)]);requests=[]
        async def handle(payload):requests.append(payload);return await normal(payload) if len(requests)<=2 else None
        worker,_,old=monitor_fixture(monkeypatch,handle);await worker.tick();p=store.status(database.DB_FILE,A)
        assert p['capability']=='averaged' and p['pending'] and p['cursor']==1 and p['records_retrieved']==1 and not old
        with closing(sqlite3.connect(passive_stats.statistics_path(database.DB_FILE,A))) as db:assert db.execute('SELECT COUNT(*) FROM neighbor_snr_aggregates').fetchone()[0]==1
        sent=len(requests);await worker.tick();assert len(requests)==sent
    asyncio.run(run())


def test_disable_after_commit_preserves_evidence_and_blocks_more_requests(station,monkeypatch):
    async def run():
        c=cfg();worker,calls,_=monitor_fixture(monkeypatch,handler_for([response(seq=i,window=i-1,ceiling=2) for i in (1,2)]));original=store.record
        def stop(*args,**kw):
            result=original(*args,**kw)
            if args[4]['record']:legacy.save_settings(database.DB_FILE,A,False,30)
            return result
        monkeypatch.setattr(store,'record',stop);await worker.tick();assert len(calls)==2
        with closing(sqlite3.connect(passive_stats.statistics_path(database.DB_FILE,A))) as db:assert db.execute('SELECT COUNT(*) FROM neighbor_snr_aggregates').fetchone()[0]==1
        assert not passive_stats.statistics_path(database.DB_FILE,B).exists()
        assert not store.record(database.DB_FILE,c,'late',UTC,wire.decode(response()),response())
    asyncio.run(run())


@pytest.mark.parametrize('action',['disconnect','shutdown','remove'])
def test_request_cancellation_cleanup(station,monkeypatch,action):
    async def run():
        cfg();entered=asyncio.Event()
        async def handle(payload):entered.set();await asyncio.Event().wait()
        worker,calls,_=monitor_fixture(monkeypatch,handle);task=asyncio.create_task(worker.tick());await entered.wait()
        if action=='remove':
            with station.db:station.db.execute('UPDATE voltage_config SET managed=0 WHERE public_key=?',(A,))
        if action=='disconnect':worker.runtime.companion.mc.connection_manager.is_connected=False
        task.cancel();await asyncio.gather(task,return_exceptions=True)
        assert len(calls)==1 and not worker.runtime.companion.control_lock.locked()
        assert not worker.runtime.companion.mc.subscriptions[EventType.BINARY_RESPONSE] and not passive_stats.statistics_path(database.DB_FILE,A).exists()
        if action!='remove':assert not legacy.due(database.DB_FILE,time.time())
    asyncio.run(run())


def test_mixed_repeaters_and_guest_permissions(station,monkeypatch):
    async def run():
        cfg()
        with station.db:voltage_store.ensure_repeater(station.db,C)
        legacy.save_settings(database.DB_FILE,C,True,30)
        worker,_,old=monitor_fixture(monkeypatch,handler_for([response()]));companion=worker.runtime.companion;commands=companion.mc.commands
        companion.mc.contacts[C]=dict(public_key=C,type=2,adv_name='Standard');original=commands.send
        async def mixed(payload,events):
            if payload[1:33]==bytes.fromhex(C):return event(EventType.MSG_SENT,expected_ack=bytes.fromhex('12345678'))
            return await original(payload,events)
        commands.send=mixed;await worker.tick();await worker.tick()
        assert store.status(database.DB_FILE,A)['capability']=='averaged' and store.status(database.DB_FILE,C)['capability']=='unknown' and old==[C]
        assert aggregate(database.DB_FILE,C,1)['neighbor_snr'][0]['source']=='legacy_last_heard'
    asyncio.run(run())


def test_before_after_weighted_means_and_incompatible_source_exclusion(station):
    from meshcorestation.storage import repeater_comparison as comparison
    c=cfg();record(c,response());record(c,response(seq=2,window=1,count=10,total=20),'after')
    with station.db:change=station.db.execute('INSERT INTO repeater_changes(public_key,recorded_at,description) VALUES(?,?,?)',(A,UTC+1800,'Antenna')).lastrowid
    result=comparison.aggregate(database.DB_FILE,A,change,1,now=UTC+3601)
    assert result['median_snr_change']==pytest.approx(1.375)
    assert (result['matched'][0]['before_samples'],result['matched'][0]['after_samples'])==(2,10)
    legacy.record_page(database.DB_FILE,c,'old-c',UTC+100,UTC+101,[dict(pubkey=C[:8],snr=8,secs_ago=5)])
    record(c,response(seq=3,window=1,key=C),'new-c');result=comparison.aggregate(database.DB_FILE,A,change,1,now=UTC+3601)
    assert result['source_changes'][0]['public_key']==C and result['median_snr_change']==pytest.approx(1.375)


def test_local_recheck_does_not_enable_or_reschedule(station):
    from flask import Flask
    from meshcorestation.web.statistics_api import register_statistics_routes
    app=Flask(__name__);register_statistics_routes(app);client=app.test_client();headers={'X-Meshcore-Control':'1'};url='/api/repeater-statistics/neighbor-monitor'
    assert client.post(url,json=dict(operation='recheck_protocol',public_key=A)).status_code==403
    before=legacy.settings(database.DB_FILE,A);result=client.post(url,headers=headers,json=dict(operation='recheck_protocol',public_key=A))
    assert result.status_code==200 and result.json['protocol']['detection']=='recheck_requested'
    assert legacy.settings(database.DB_FILE,A)==before and not passive_stats.statistics_path(database.DB_FILE,A).exists()
    assert client.post(url,headers=headers,json=dict(operation='recheck_protocol',public_key=B)).status_code==400


def test_clock_worker_interaction_preserves_admin_enforcement(station,monkeypatch):
    from meshcorestation.radio import clock_sync
    from meshcorestation.storage import clock_sync as clocks
    async def run():
        cfg();worker,calls,_=monitor_fixture(monkeypatch,handler_for([response()]));clocks.save(database.DB_FILE,A,True,24,0)
        with closing(connect(database.DB_FILE)) as db,db:db.execute('UPDATE repeater_clock_sync SET next_due=0')
        monkeypatch.setattr(clock_sync,'synchronized_host_time',AsyncMock(return_value=int(time.time())))
        clock=clock_sync.ClockSyncWorker(worker.runtime,database.DB_FILE)
        async with worker.runtime.companion.control_lock:
            a=asyncio.create_task(worker.tick());b=asyncio.create_task(clock.tick());await asyncio.sleep(.03);assert not calls
        await asyncio.gather(a,b)
        assert store.status(database.DB_FILE,A)['capability']=='averaged'
        assert 'Administrator authorization unavailable' in clocks.settings(database.DB_FILE,A)['error']
    asyncio.run(run())


def test_long_interval_retention_warning(station,monkeypatch):
    async def run():
        legacy.save_settings(database.DB_FILE,A,True,1440);worker,_,_=monitor_fixture(monkeypatch,handler_for([]));await worker.tick()
        assert 'retention' in store.status(database.DB_FILE,A)['warning'] and legacy.settings(database.DB_FILE,A)['interval_minutes']==1440
    asyncio.run(run())


def test_fixed_snapshot_excludes_new_completions_until_next_poll(station,monkeypatch):
    async def run():
        cfg();rows=[response(seq=i,window=i-1,ceiling=2) for i in (1,2)]
        worker,calls,_=monitor_fixture(monkeypatch,handler_for(rows));monkeypatch.setattr(collection,'MAX_RECORDS',1)
        await worker.tick();rows.append(response(seq=3,window=2,ceiling=3));make_due();await worker.tick()
        assert store.status(database.DB_FILE,A)['cursor']==2 and not store.status(database.DB_FILE,A)['pending']
        assert struct.unpack('<BBBB16sII',calls[-1][33:])[5]==2
        make_due();await worker.tick();assert store.status(database.DB_FILE,A)['cursor']==3
    asyncio.run(run())


def test_early_oversized_reply_is_protocol_error_not_unreachable():
    async def run():
        async def handle(payload):return b'x'*200
        companion,_,_=transport_fixture(handle)
        async with companion.control_lock:
            with pytest.raises(wire.ProtocolError):await wire.exchange(companion,companion.mc.contacts[A],wire.request(),timeout=.02)
        assert not companion.mc.subscriptions[EventType.BINARY_RESPONSE]
    asyncio.run(run())


def test_interrupted_poll_recovery_and_low_disk_safety(station,monkeypatch):
    c=cfg();raw=response();assert store.record(database.DB_FILE,c,'unfinished',UTC,wire.decode(raw),raw)
    store.recover_collection(database.DB_FILE,A)
    path=passive_stats.statistics_path(database.DB_FILE,A)
    with closing(sqlite3.connect(path)) as db:
        row=db.execute('SELECT finished_at,error FROM neighbor_snr_aggregate_collections').fetchone();assert row[0] and 'interrupted' in row[1]
    monkeypatch.setattr(store.shutil,'disk_usage',lambda _:NS(free=0))
    with pytest.raises(OSError,match='Low disk'):store.record(database.DB_FILE,c,'full',UTC,wire.decode(response(seq=2,window=1)),response(seq=2,window=1))
    with closing(sqlite3.connect(path)) as db:assert db.execute('SELECT COUNT(*) FROM neighbor_snr_aggregates').fetchone()[0]==1
