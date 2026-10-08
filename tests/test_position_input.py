import asyncio
import sqlite3
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
import pytest
from meshcorestation.commands.actions import execute, parse_coordinates
from meshcorestation.storage import command_store

@pytest.mark.parametrize('text,expected',[('49.123456, 8.654321',(49.123456,8.654321)),('-49.5 +8.2',(-49.5,8.2)),(' 90, -180 ',(90,-180)),('.5,.6',(.5,.6))])
def test_coordinate_formats(text,expected):
    assert parse_coordinates(text)==expected

@pytest.mark.parametrize('text',['0,0','91,8','49,-181','nan,8','inf,8','49,8,100','49.1','foo','49,1 8,2','1e3,8'])
def test_bad_coordinates(text):
    with pytest.raises(ValueError):parse_coordinates(text)

@pytest.mark.parametrize('arguments,contact,success',[('49.123456, 8.654321',{'public_key':'abc','adv_name':'zebbel'},True),('49,8',None,False),('wrong',{'public_key':'abc','adv_name':'zebbel'},False)])
def test_message_input_never_requests_telemetry(arguments,contact,success):
    async def scenario():
        companion=NS(get_sender_contact=AsyncMock(return_value=contact),get_telemetry=AsyncMock(),send_channel_message=AsyncMock())
        bot=NS(companion=companion,database=Mock(),logger=Mock(),position_update_running=False)
        result=await execute(bot,'position',{'name':'zebbel','message':'renamed '+arguments},{})
        assert result.ok==success
        companion.get_telemetry.assert_not_called();companion.send_channel_message.assert_not_called()
        if success:
            bot.database.save_companion_position.assert_called_once_with('abc','zebbel',49.123456,8.654321,None)
            assert result.values['latitude']==49.123456
        else:bot.database.save_companion_position.assert_not_called()
        assert not bot.position_update_running
    asyncio.run(scenario())

def test_position_template_migration_is_scoped_and_idempotent():
    db=sqlite3.connect(':memory:')
    command_store.initialize(db,legacy=True)
    db.execute("UPDATE bot_commands SET reply='Hi @{sender_name}: {result}',failure_reply='@{sender_name}: failed' WHERE action='position'")
    command_store.initialize(db);command_store.initialize(db)
    commands=command_store.read(db);position=next(c for c in commands if c['action']=='position')
    assert position['reply']=='Hi @[{sender_name}]: {result}'
    assert position['failure_reply']=='@[{sender_name}]: failed'
    assert next(c for c in commands if c['trigger']=='status')['reply'].startswith('@{sender_name}')
