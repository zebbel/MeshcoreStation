"""Room bot ping should render direct-path labels and measured distances."""
import asyncio
from types import SimpleNamespace

from meshcorestation.commands.context import collect
from meshcorestation.commands.templates import render
from meshcorestation.radio.bot import Bot


KEY = 'ab' * 32
PING = '@{sender_name} | {hop_count} hops | SNR {snr} | RSSI {rssi} dBm | route {route_distance}km | scope {scope_name}.'


class FakeDB:
    def get_companion_position(self, key):
        assert key == KEY
        return dict(public_key=KEY, latitude=49.5, longitude=8.2)

    def get_companion_positions_by_name(self, name):
        raise AssertionError('Room identities must be resolved by key, not nickname')

    def get_repeaters_by_prefix(self, prefix):
        return [dict(public_key='ab' * 32, latitude=49.7, longitude=8.3)] if prefix == 'ab' else []

    def get_repeater_count(self):
        return 1


class FakeCompanion:
    channel_name = 'legacy-channel'

    def _get_message_hops(self, message):
        return message.get('path_len')

    async def get_self_info(self):
        return dict(adv_lat=50.0, adv_lon=8.5)


def ping(rx, path_len, *, missing_position=False):
    db = FakeDB()
    if missing_position:
        db.get_companion_position = lambda key: None
    companion = FakeCompanion()
    bot = Bot(SimpleNamespace(warning=lambda *args: None), companion, db)
    message = dict(name='Alex', message='ping', room_id=7, room_name='Bot room',
                   sender_public_key=KEY, path_len=path_len,
                   path='direct' if path_len is None else f'{path_len} hops')
    needed = {'hop_count', 'snr', 'rssi', 'route_distance', 'scope_name',
              'sender_public_key', 'channel_name', 'path', 'direct_distance'}
    values = asyncio.run(collect(bot, needed, message, rx, []))
    return values, render(PING, values)


def test_scoped_room_flood_ping_reports_full_metadata():
    rx = dict(path_len=1, path_hash_size=1, path='ab', snr=6.5,
              rssi=-94, room_scope_name='Europe', route_type=0)
    values, reply = ping(rx, 1)
    assert values['sender_public_key'] == KEY
    assert values['channel_name'] == 'Bot room'
    assert values['hop_count'] == 1
    assert values['direct_distance'] > 0
    assert values['route_distance'].value > 0
    assert '1 hops' in reply
    assert 'SNR 6.5' in reply and 'RSSI -94' in reply
    assert 'route unknown' not in reply and 'scope Europe' in reply


def test_direct_room_ping_reports_direct_hops_scope_and_straight_line_route():
    rx = dict(path_len=None, path_hash_size=None, path='', route_type=2,
              snr=-3.5, rssi=-112, room_scope_name='direct')
    values, reply = ping(rx, None)
    assert values['sender_public_key'] == KEY
    assert values['hop_count'].reason == 'direct'
    assert values['path'] == 'direct'
    assert values['route_distance'].value == values['direct_distance']
    assert f'route {values["direct_distance"]:.2f}km' in reply
    assert ' | direct | ' in reply
    assert 'direct hops' not in reply
    assert '(direct)' not in reply
    assert 'SNR -3.5' in reply and 'RSSI -112' in reply
    assert 'scope direct' in reply


def test_direct_room_route_without_coordinates_remains_unknown():
    rx = dict(path_len=None, path_hash_size=None, path='', route_type=2,
              snr=1.5, rssi=-80, room_scope_name='direct')
    values, reply = ping(rx, None, missing_position=True)
    assert values['hop_count'].reason == 'direct'
    assert values.get('direct_distance') is None
    assert values.get('route_distance') is None
    assert 'route unknown' in reply
    assert 'scope direct' in reply


def test_numeric_invalid_values_still_render_unknown():
    assert render('SNR {snr}', {'snr':'unverified'}) == 'SNR unknown'
