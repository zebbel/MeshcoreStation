import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from meshcorestation.radio.repeater_control import RepeaterControl


@pytest.mark.parametrize('value,expected', [(1791900000,1791900000),(0,0),(None,None),('123',None),(True,None),(-1,None),(2**32,None)])
def test_clock_timestamp(value,expected):
    assert RepeaterControl.clock_timestamp({'server_timestamp':value}) == expected
    assert RepeaterControl.clock_timestamp({}) is None


def test_status_passes_remote_clock_without_extra_radio_requests():
    key='ab'*32
    commands=NS(req_status_sync=AsyncMock(return_value={'pubkey_pre':key[:12],'uptime':100}))
    control=RepeaterControl(NS(mc=NS(commands=commands)))
    contact={'public_key':key,'adv_name':'Repeater','type':2}
    control.transport=NS(contact=AsyncMock(return_value=contact),login=AsyncMock(return_value={'is_admin':False,'server_timestamp':1791900000}))
    async def scenario():
        login=await control.execute({'action':'login','public_key':key})
        result=await control.execute({'action':'status','public_key':key,'session':login['session']})
        assert result['repeater_time']==1791900000
        assert result['sampled_at']!=result['repeater_time']
    asyncio.run(scenario())
    commands.req_status_sync.assert_awaited_once()
