from meshcorestation.web.layout import build_layout
from dash import html


def walk(node):
    yield node
    children=getattr(node,'children',[])
    if not isinstance(children,list):children=[children]
    for child in children:
        if hasattr(child,'to_plotly_json'):yield from walk(child)


def test_latest_command_and_button_remain_in_closed_summary():
    nodes=list(walk(build_layout()))
    ids=[getattr(n,'id',None) for n in nodes if getattr(n,'id',None)]
    assert len(ids)==len(set(ids))
    history=next(n for n in nodes if getattr(n,'id',None)=='command-history-disclosure')
    summary=history.children[0]
    assert {'last-command','last-detail','open-commands'} <= {getattr(n,'id',None) for n in walk(summary)}
    assert not getattr(history,'open',False)
    cards=next(n for n in nodes if getattr(n,'className',None)=='cards')
    assert len(cards.children)==2
    assert 'open-repeater-statistics' not in ids
    assert 'repeater-statistics-inline' in ids
    room=next(n for n in nodes if getattr(n,'id',None)=='room-server-disclosure')
    assert not getattr(room, 'open', False)
    room_iframe=next(n for n in walk(room) if getattr(n,'id',None)=='room-server-frame')
    assert room_iframe.src=='/rooms?embedded=1'
    assert room_iframe.style['height']=='160px'
    assert ids.index('room-server-disclosure') < ids.index('repeater-management-disclosure')


def test_repeater_section_groups_selection_battery_and_statistics():
    nodes=list(walk(build_layout()))
    management=next(n for n in nodes if getattr(n,'id',None)=='repeater-management-disclosure')
    ids=[getattr(n,'id',None) for n in walk(management)]
    assert not getattr(management, 'open', False)
    assert ids.index('managed-repeater') < ids.index('battery-overview') < ids.index('repeater-statistics-inline')
    assert {'managed-repeater-add','managed-repeater-open','open-voltage'} <= set(ids)
    # The dropdown takes its own full-width row; actions share the next row.
    controls=next(n for n in walk(management) if getattr(n,'className',None)=='managed-repeater-controls')
    assert len(controls.children)==2
    assert [getattr(n,'id',None) for n in walk(controls.children[0]) if getattr(n,'id',None)] == ['managed-repeater']
    actions=controls.children[1]
    assert actions.className=='managed-repeater-actions'
    assert [n.id for n in walk(actions) if getattr(n,'id',None)] == [
        'managed-repeater-add','managed-repeater-open','managed-repeater-remove'
    ]
    assert 'select-voltage-repeater' not in [getattr(n,'id',None) for n in nodes]


def test_every_dashboard_disclosure_starts_collapsed():
    nodes=list(walk(build_layout()))
    for item in nodes:
        if isinstance(item, html.Details):
            assert not getattr(item, 'open', False), f"{getattr(item, 'id', 'unnamed')} starts expanded"
    sections={getattr(item, 'id', None) for item in nodes if isinstance(item, html.Details)}
    assert {'room-server-disclosure', 'repeater-management-disclosure',
            'repeater-statistics-disclosure', 'command-history-disclosure'} <= sections
