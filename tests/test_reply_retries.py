"""Protocol timing and bounded asynchronous saved-text retries. No RF or wall-clock waits."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,Mock
import pytest
from meshcore import EventType
from test_reply_tracking import db,packet,KEY
from meshcorestation.radio.companion import Companion
from meshcorestation.radio.reply_retries import timing,retry_delay
from meshcorestation.storage import reply_store as store

INFO={'name':'Station','public_key':'aa'*32,'radio_freq':869.525,'radio_sf':7,'radio_bw':125.0,'radio_cr':5}


def setup(db,hops=1):
    c=Companion(Mock(),db);c.channel_idx=0;c.channel_name='Public';c.tracking_key=KEY
    c.active_command_id=1;c.active_command_hops=hops
    sent=[];scopes=[];waits=[]
    async def send(channel,message,timestamp):
        sent.append((channel,message,timestamp));return NS(type=EventType.OK)
    async def scope(value):scopes.append(value);return NS(type=EventType.OK)
    c.mc=NS(self_info=dict(INFO),connection_manager=NS(is_connected=True),commands=NS(
        send_chan_msg=send,set_flood_scope=scope,get_stats_core=AsyncMock(return_value=NS(type=EventType.STATS_CORE,payload={'queue_len':0}))))
    c.get_self_info=AsyncMock(return_value=dict(INFO))
    async def wait(job,seconds):waits.append(seconds);await asyncio.sleep(0)
    c.reply_retries.wait=wait
    return c,sent,scopes,waits


async def finish(c):
    await asyncio.gather(*(j.task for j in tuple(c.reply_retries.jobs.values())))


def test_timing_matches_transmitted_encryption_padding_and_radio_parameters():
    r=timing(INFO,'pong',False)
    assert r['packet_bytes']==len(packet()['pkt_payload'])+2==37
    assert r['airtime']==pytest.approx(.106752)
    assert r['timeout']==pytest.approx((500+16*106)/1000*1.2)
    assert timing(INFO,'pong',True)['packet_bytes']==41
    assert timing(INFO,'🐝'*30,False)['airtime']>r['airtime']
    assert timing({**INFO,'radio_sf':11},'pong',False)['airtime']==pytest.approx(1.200128)
    assert timing({**INFO,'radio_bw':250},'pong',False)['airtime']==pytest.approx(r['airtime']/2)
    assert timing({**INFO,'radio_cr':8},'pong',False)['airtime']>r['airtime']
    # Firmware truncates name-prefixed channel text before encrypting.
    assert timing(INFO,'x'*500,False)==timing(INFO,'x'*151,False)
    assert timing({**INFO,'radio_sf':5},'pong',False)['airtime']>0
    for field,value in [('radio_sf',None),('radio_sf',True),('radio_bw',float('nan')),('radio_cr',4),('name','')]:
        with pytest.raises(ValueError):timing({**INFO,field:value},'pong',False)
    with pytest.raises(ValueError):timing({**INFO,'radio_sf':12,'radio_bw':7.8},'x'*100,False)


@pytest.mark.parametrize('hops,count',[(0,2),(1,4),(63,4),(None,1),(-1,1)])
def test_attempt_limits_saved_text_original_channel_scope_and_unique_timestamps(db,hops,count,monkeypatch):
    async def run():
        c,sent,scopes,waits=setup(db,hops);secret=b'abcdefghijklmnop'
        c._get_reply_scope=lambda rx:('original scope',secret)
        monkeypatch.setattr('meshcorestation.radio.companion.time.time',lambda:1000)
        monkeypatch.setattr('meshcorestation.radio.reply_retries.random.uniform',lambda a,b:2.5)
        await c.send_channel_message(0,'saved pong',{})
        assert len(sent)==1 # Scheduled in the background; never blocks command handling.
        await finish(c)
        assert len(sent)==count and {s[:2] for s in sent}=={(0,'saved pong')}
        assert len({s[2] for s in sent})==count
        assert scopes==[secret,None]*count
        assert waits==[(20 if hops==0 else 30)+2.5]*(count-1)
        row=store.snapshot(db.db,1)['replies'][0]
        assert len(row['attempts'])==count
        assert [a['attempt'] for a in row['attempts']]==list(range(1,count+1))
        assert all(a['send_status']=='accepted' for a in row['attempts'])
        assert row['retry_status']==('exhausted' if count>1 else 'not scheduled')
        assert row['next_retry_at'] is None
    asyncio.run(run())


@pytest.mark.parametrize('hops,cancel',[(0,False),(1,True)])
def test_authenticated_forwarding_cancels_only_multihop_and_zero_path_does_not(db,hops,cancel):
    async def run():
        c,sent,_,_=setup(db,hops)
        async def wait(job,seconds):
            # An authenticated but zero-hop copy is not forwarding evidence.
            c._handle_rx_log(NS(payload=packet(stamp=sent[0][2],path='')))
            assert not job.stop.is_set()
            # Normal RX callback authenticates the saved timestamp/text/channel.
            c._handle_rx_log(NS(payload=packet(stamp=sent[0][2])))
            await asyncio.sleep(0)
        c.reply_retries.wait=wait
        await c.send_channel_message(0,'pong',{'route_type':1});await finish(c)
        assert len(sent)==(1 if cancel else 2)
        row=store.snapshot(db.db,1)['replies'][0]
        assert row['retry_status']==('forwarding observed' if cancel else 'exhausted')
        assert row['observations'] and 'unconfirmed' in row['retry_detail']
    asyncio.run(run())


def test_forwarding_for_earlier_attempt_stops_remaining_attempts(db):
    async def run():
        c,sent,_,_=setup(db)
        async def wait(job,seconds):
            if len(sent)==2:c._handle_rx_log(NS(payload=packet(stamp=sent[0][2])))
            await asyncio.sleep(0)
        c.reply_retries.wait=wait
        await c.send_channel_message(0,'pong',{'route_type':1});await finish(c)
        assert len(sent)==2 and store.snapshot(db.db,1)['replies'][0]['retry_status']=='forwarding observed'
    asyncio.run(run())


@pytest.mark.parametrize('change',['wrong text','wrong channel','wrong scope','wrong mac'])
def test_unrelated_or_unauthenticated_evidence_does_not_cancel(db,change):
    async def run():
        c,sent,_,_=setup(db)
        async def wait(job,seconds):
            p=packet(stamp=sent[0][2],text='Station: other' if change=='wrong text' else 'Station: pong',
                     key=b'abcdefghijklmnop' if change=='wrong channel' else KEY,
                     scope=b'abcdefghijklmnop' if change=='wrong scope' else None)
            if change=='wrong mac':p['pkt_payload']=p['pkt_payload'][:1]+b'xx'+p['pkt_payload'][3:]
            c._handle_rx_log(NS(payload=p));await asyncio.sleep(0)
        c.reply_retries.wait=wait
        await c.send_channel_message(0,'pong',{'route_type':1});await finish(c)
        assert len(sent)==4
    asyncio.run(run())


@pytest.mark.parametrize('cause',['configuration','disconnect','radio changed','identity changed','queue busy','queue unknown','budget'])
def test_safety_cancellation_and_bounded_queue_deferrals(db,cause):
    async def run():
        c,sent,_,waits=setup(db)
        if cause=='radio changed':c.get_self_info.return_value={**INFO,'radio_bw':250}
        if cause=='identity changed':c.get_self_info.return_value={**INFO,'public_key':'bb'*32}
        if cause=='queue busy':c.mc.commands.get_stats_core.return_value.payload['queue_len']=1
        if cause=='queue unknown':c.mc.commands.get_stats_core.return_value=NS(type=EventType.ERROR,payload={})
        if cause=='budget':c.reply_retries.budget.append((c.reply_retries.clock(),60))
        await c.send_channel_message(0,'pong',{'route_type':1})
        if cause=='configuration':c.reply_retries.cancel('Configuration changed.')
        if cause=='disconnect':c.mc.connection_manager.is_connected=False
        await finish(c)
        assert len(sent)==1 and not c.reply_retries.jobs
        assert store.snapshot(db.db,1)['replies'][0]['retry_status']=='cancelled'
        if cause.startswith('queue'):assert len(waits)==3
    asyncio.run(run())


def test_shutdown_before_worker_starts_and_restart_never_replays(db):
    async def run():
        c,sent,_,_=setup(db)
        await c.send_channel_message(0,'pong',{'route_type':1})
        await c.reply_retries.close()
        assert len(sent)==1 and store.snapshot(db.db,1)['replies'][0]['retry_status']=='cancelled'
        store.retry_state(db.db,1,'pending','Simulated power loss',100)
        other=Companion(Mock(),db)
        assert not other.reply_retries.jobs
        assert store.snapshot(db.db,1)['replies'][0]['retry_status']=='cancelled'
    asyncio.run(run())


def test_command_executes_once_and_split_parts_have_independent_limits(db):
    async def run():
        c,sent,_,_=setup(db,0);c.active_command_id=None
        c.bot=NS(match_command=lambda text:{'trigger':'ping'},handle_message=AsyncMock(return_value='x'*180))
        c._find_matching_rx=lambda msg:{'route_type':1}
        event=NS(payload={'channel_idx':0,'text':'Alice: ping','sender_timestamp':900,'path_len':0})
        await c._handle_channel_message(event);await finish(c)
        await c._handle_channel_message(event) # Existing persistent reception deduplication.
        assert c.bot.handle_message.await_count==1 and len(sent)==4
        command=db.db.execute('SELECT max(id) FROM logger').fetchone()[0]
        rows=store.snapshot(db.db,command)['replies']
        assert len(rows)==2 and all(len(r['attempts'])==2 for r in rows)
        assert all(len({a['timestamp'] for a in r['attempts']})==2 for r in rows)
    asyncio.run(run())


def test_rejected_submission_can_retry_and_records_each_acceptance(db):
    async def run():
        c,sent,_,_=setup(db,0)
        original=c.mc.commands.send_chan_msg
        async def send(*args,**kwargs):
            result=await original(*args,**kwargs)
            return NS(type=EventType.ERROR) if len(sent)==1 else result
        c.mc.commands.send_chan_msg=send
        assert await c.send_channel_message(0,'pong',{'route_type':1}) is False
        await finish(c)
        assert [a['send_status'] for a in store.snapshot(db.db,1)['replies'][0]['attempts']]==['rejected','accepted']
    asyncio.run(run())


def test_control_lock_cancellation_and_config_dispatch_do_not_rerun_command(db):
    async def run():
        from meshcorestation.runtime import Runtime
        c,sent,_,_=setup(db)
        runtime=Runtime(Mock(),db);runtime.companion=c
        runtime.control=NS(execute=AsyncMock(return_value={'ok':True}))
        await c.send_channel_message(0,'pong',{'route_type':1})
        await runtime.dispatch({'operation':'radio'})
        await finish(c)
        assert len(sent)==1 and store.snapshot(db.db,1)['replies'][0]['retry_status']=='cancelled'
        runtime.control.execute.assert_awaited_once()
    asyncio.run(run())


def test_bounded_pending_jobs_and_unknown_radio_fail_closed(db,monkeypatch):
    async def run():
        c,sent,_,_=setup(db)
        c.mc.self_info.pop('radio_sf')
        await c.send_channel_message(0,'pong',{'route_type':1})
        assert not c.reply_retries.jobs and len(sent)==1
        assert 'SF/BW/CR' in store.snapshot(db.db,1)['replies'][0]['retry_detail']
        c.mc.self_info=dict(INFO);monkeypatch.setattr('meshcorestation.radio.reply_retries.MAX_PENDING',0)
        await c.send_channel_message(0,'second',{'route_type':1})
        assert not c.reply_retries.jobs and len(sent)==2
        assert 'safety limit' in store.snapshot(db.db,1)['replies'][1]['retry_detail']
    asyncio.run(run())


def test_queue_check_race_forwarding_prevents_send(db):
    async def run():
        c,sent,_,_=setup(db)
        async def stats():
            c._handle_rx_log(NS(payload=packet(stamp=sent[0][2])))
            return NS(type=EventType.STATS_CORE,payload={'queue_len':0})
        c.mc.commands.get_stats_core=stats
        await c.send_channel_message(0,'pong',{'route_type':1});await finish(c)
        assert len(sent)==1
    asyncio.run(run())


def test_cancel_inflight_submission_records_uncertainty_and_resets_scope(db):
    async def run():
        c,sent,scopes,_=setup(db)
        entered=asyncio.Event()
        original=c.mc.commands.send_chan_msg
        async def send(*args,**kwargs):
            result=await original(*args,**kwargs)
            if len(sent)>1:
                entered.set();await asyncio.Future()
            return result
        c.mc.commands.send_chan_msg=send
        await c.send_channel_message(0,'pong',{'route_type':1});await entered.wait()
        await c.reply_retries.close()
        row=store.snapshot(db.db,1)['replies'][0]
        assert row['retry_status']=='cancelled' and row['attempts'][1]['send_status']=='uncertain'
        assert scopes[-1] is None and not c.reply_lock.locked() and not c.control_lock.locked()
    asyncio.run(run())


def test_additive_schema_migration_preserves_old_reply(db):
    root=store.begin(db.db,1,'old reply','Station',KEY,123,'unscoped',None,now=123)
    store.finish(db.db,root,'accepted')
    with db.db:db.db.execute('ALTER TABLE command_replies DROP COLUMN retry_status')
    store.initialize(db.db)
    row=store.snapshot(db.db,1)['replies'][0]
    assert row['message']=='old reply' and row['timestamp']==123 and row['send_status']=='accepted'
    assert row['retry_status']=='legacy' and len(row['attempts'])==1


def test_closed_session_cannot_schedule_new_work(db):
    async def run():
        c,sent,_,_=setup(db)
        await c.send_channel_message(0,'pong',{'route_type':1})
        await c.reply_retries.close()
        assert await c.send_channel_message(0,'late reply',{'route_type':1}) is False
        assert not c.reply_retries.jobs and len(sent)==1
        assert store.snapshot(db.db,1)['replies'][0]['retry_status']=='cancelled'
    asyncio.run(run())


def test_real_async_timer_is_interruptible_without_waiting_for_timeout(db):
    async def run():
        c,sent,_,_=setup(db)
        c.reply_retries.wait=c.reply_retries._wait
        await c.send_channel_message(0,'pong',{'route_type':1})
        await asyncio.sleep(0)
        c.reply_retries.cancel('Configuration changed.')
        await asyncio.wait_for(finish(c),1)
        assert len(sent)==1
    asyncio.run(run())


def test_scoped_forwarding_must_match_original_scope(db):
    async def run():
        c,sent,_,_=setup(db)
        db.add_scope('original');secret=bytes.fromhex(db.get_scopes()[0]['scope_key'])
        c._get_reply_scope=lambda rx:('original',secret)
        async def wait(job,seconds):
            c._handle_rx_log(NS(payload=packet(stamp=sent[0][2])))
            assert not job.stop.is_set(),'unscoped echo must not stop a scoped reply'
            c._handle_rx_log(NS(payload=packet(stamp=sent[0][2],scope=secret)))
            assert job.stop.is_set()
            await asyncio.sleep(0)
        c.reply_retries.wait=wait
        await c.send_channel_message(0,'pong',{});await finish(c)
        assert len(sent)==1
        assert store.snapshot(db.db,1)['replies'][0]['retry_status']=='forwarding observed'
    asyncio.run(run())


@pytest.mark.parametrize('hops,protocol,minimum',[(0,2.6,20),(1,2.6,30),(63,2.6,30),(0,45,45),(1,45,45)])
def test_retry_delay_minimum_protocol_precedence_and_jitter_bounds(monkeypatch,hops,protocol,minimum):
    for jitter in (0,2.5,5):
        def draw(low,high):
            assert (low,high)==(0,5)
            return jitter
        monkeypatch.setattr('meshcorestation.radio.reply_retries.random.uniform',draw)
        assert retry_delay(protocol,hops)==minimum+jitter
    assert retry_delay(protocol,None) is None


def test_multihop_cumulative_timing_and_saved_next_attempt_time(db,monkeypatch):
    async def run():
        c,sent,_,waits=setup(db,1)
        jitter=iter([0,2.5,5]);elapsed=0;attempt_times=[]
        monkeypatch.setattr('meshcorestation.radio.reply_retries.random.uniform',lambda a,b:next(jitter))
        monkeypatch.setattr('meshcorestation.radio.reply_retries.time.time',lambda:1000+elapsed)
        async def wait(job,seconds):
            nonlocal elapsed
            row=store.snapshot(db.db,1)['replies'][0]
            assert row['next_retry_at']==1000+elapsed+seconds
            assert f'{seconds:.1f}s' in row['retry_detail']
            waits.append(seconds);elapsed+=seconds;attempt_times.append(elapsed)
            await asyncio.sleep(0)
        c.reply_retries.wait=wait
        await c.send_channel_message(0,'pong',{'route_type':1});await finish(c)
        assert waits==[30,32.5,35] and attempt_times==[30,62.5,97.5]
        assert len(sent)==4
    asyncio.run(run())
