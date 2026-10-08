import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
import pytest
from meshcore import EventType
from meshcorestation.radio.companion import Companion
from meshcorestation.commands.actions import sender_position


@pytest.mark.parametrize('key', [None, b'1234567890123456'])
@pytest.mark.parametrize('failure', ['none','timeout','error','cancel','select','reset'])
def test_telemetry_scope_restored(key, failure):
    async def scenario():
        calls=[]
        async def scope(value):
            calls.append(('scope',value))
            return NS(type=EventType.ERROR if failure=='select' and value is not None else EventType.OK)
        async def reset(key):
            calls.append(('reset',key))
            return NS(type=EventType.ERROR if failure=='reset' else EventType.OK)
        async def telemetry(contact,timeout):
            calls.append(('telemetry',timeout))
            if failure=='error': raise RuntimeError('radio error')
            if failure=='cancel': raise asyncio.CancelledError()
            return None if failure=='timeout' else [{'type':'gps'}]
        contact={'adv_name':'Alice','public_key':'abc'}
        commands=NS(get_contacts=AsyncMock(return_value=NS(type=EventType.CONTACTS,payload={'abc':contact})),set_flood_scope=scope,reset_path=reset,req_telemetry_sync=telemetry)
        companion=Companion.__new__(Companion)
        companion.mc=NS(commands=commands); companion.logger=Mock(); companion.reply_lock=asyncio.Lock()
        companion._get_reply_scope=Mock(return_value=('region' if key else 'unscoped',key))
        if failure in ('error','cancel'):
            with pytest.raises(RuntimeError if failure=='error' else asyncio.CancelledError):
                await companion.get_telemetry('Alice',{'rx':1})
        else:
            response=await companion.get_telemetry('Alice',{'rx':1})
            assert (response is not None)==(failure=='none')
        assert calls[0]==('scope',key if key else '*')
        assert calls[-1]==('scope',None)
        assert not companion.reply_lock.locked()
        if failure in ('select','reset'): assert not any(c[0]=='telemetry' for c in calls)
    asyncio.run(scenario())


@pytest.mark.parametrize('ack_ok',[True,False])
def test_acknowledgment_before_telemetry(ack_ok):
    async def scenario():
        calls=[]; rx={'route_type':1}
        async def send(channel,text,matched):
            calls.append('ack'); assert matched is rx; assert 'Requesting telemetry' in text; assert text.startswith('@[Alice]')
            return 'unscoped' if ack_ok else False
        async def telemetry(name,matched):
            calls.append('telemetry'); assert matched is rx
            return {'contact':{'public_key':'abc','adv_name':'Alice'},'telemetry':[{'type':'gps','channel':1,'value':{'latitude':50,'longitude':8}}]}
        bot=NS(position_update_running=False,logger=Mock(),database=Mock(),companion=NS(channel_idx=1,_get_reply_scope=lambda rx:('unscoped',None),send_channel_message=send,get_telemetry=telemetry))
        result=await sender_position(bot,'Alice',rx)
        assert result.ok==ack_ok
        assert calls==(['ack','telemetry'] if ack_ok else ['ack'])
        assert not bot.position_update_running
    asyncio.run(scenario())


def test_unknown_scope_does_not_send():
    async def scenario():
        companion=NS(_get_reply_scope=lambda rx:(None,None),send_channel_message=AsyncMock(),get_telemetry=AsyncMock())
        bot=NS(position_update_running=False,companion=companion,logger=Mock())
        assert not (await sender_position(bot,'Alice',{})).ok
        companion.send_channel_message.assert_not_called()
        companion.get_telemetry.assert_not_called()
    asyncio.run(scenario())
