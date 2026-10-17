import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from meshcorestation.radio.repeater_control import RepeaterControl
from meshcorestation.radio.repeater_fields import parse_value, validate

KEY = 'ab' * 32


def setup_control():
    control = RepeaterControl(NS(mc=NS(commands=NS())))
    control.transport = NS(contact=AsyncMock(return_value={'public_key': KEY, 'type': 2}),
                           login=AsyncMock(return_value={'is_admin': True}),
                           cli=AsyncMock(return_value='> Test'))
    return control


def run_console(command='get name', **options):
    control = setup_control()
    async def scenario():
        login = await control.execute({'action': 'login', 'public_key': KEY})
        token = login['session']
        control.sessions[token]['values']['name'] = 'Old'
        result = await control.execute(dict(action='console', public_key=KEY, session=token,
                                            command=command, confirm=True, **options))
        return token, result
    token, result = asyncio.run(scenario())
    return control, token, result


def test_console_sends_once_and_invalidates_cached_configuration():
    control, token, result = run_console()
    assert result['reply'] == '> Test'
    assert control.sessions[token]['values'] == {}
    assert control.transport.cli.await_count == 1
    assert control.transport.cli.call_args.args[1] == 'get name'


@pytest.mark.parametrize('command', ['password secret', 'get guest.password', 'set bridge.secret abc', 'set prv.key abc'])
def test_secret_responses_hidden(command):
    _, _, result = run_console(command)
    assert result['reply'] == 'Sensitive command response hidden.'


def test_reboot_does_not_wait_for_reply_and_retires_session():
    control, token, result = run_console('reboot')
    assert result['expired'] is True
    assert token not in control.sessions
    assert control.transport.cli.call_args.kwargs == {'expect_reply': False}


@pytest.mark.parametrize('command', ['', 'get name\nreboot', 'get\x00name', 'x'*148, 'é'*74])
def test_invalid_command_not_sent(command):
    control = setup_control()
    async def scenario():
        login = await control.execute({'action': 'login', 'public_key': KEY})
        with pytest.raises(ValueError):
            await control.execute(dict(action='console', public_key=KEY, session=login['session'], command=command, confirm=True))
    asyncio.run(scenario())
    control.transport.cli.assert_not_awaited()


@pytest.mark.parametrize('guest,confirmed', [(True, True), (False, False)])
def test_console_requires_current_admin_and_confirmation(guest, confirmed):
    control = setup_control()
    async def scenario():
        login = await control.execute({'action': 'login', 'public_key': KEY})
        control.transport.login.return_value = {'is_admin': not guest}
        with pytest.raises(ValueError):
            await control.execute(dict(action='console', public_key=KEY, session=login['session'], command='get name', confirm=confirmed))
    asyncio.run(scenario())
    control.transport.cli.assert_not_awaited()


def test_timeout_not_retried():
    control = setup_control()
    control.transport.cli.side_effect = asyncio.TimeoutError
    async def scenario():
        login = await control.execute({'action':'login', 'public_key':KEY})
        with pytest.raises(ValueError, match='may have applied'):
            await control.execute(dict(action='console', public_key=KEY, session=login['session'], command='set name Test', confirm=True))
    asyncio.run(scenario())
    assert control.transport.cli.await_count == 1


@pytest.mark.parametrize('field,reply,value', [('gps','on, active, no fix','on'), ('powersaving','off','off'), ('bridge.source','> logRx','rx'), ('gps.advert','> share','share')])
def test_special_read_formats(field, reply, value):
    assert parse_value(field, reply) == value


def test_corrected_numeric_limits():
    assert validate('agc.reset.interval', '1020') == '1020'
    with pytest.raises(ValueError): validate('agc.reset.interval', '1021')
    with pytest.raises(ValueError): validate('multi.acks', '2')


def test_power_saving_read_write_commands_and_readback():
    control = setup_control()
    control.transport.cli.side_effect = ['off', 'off', 'on - After 2 minutes', 'on']
    async def scenario():
        login = await control.execute({'action':'login', 'public_key':KEY})
        base = dict(public_key=KEY, session=login['session'], field='powersaving')
        await control.execute(dict(base, action='read'))
        result = await control.execute(dict(base, action='write', value='on', expected='off', confirm=True))
        assert result['value'] == 'on'
    asyncio.run(scenario())
    assert [call.args[1] for call in control.transport.cli.await_args_list] == ['powersaving', 'powersaving', 'powersaving on', 'powersaving']
