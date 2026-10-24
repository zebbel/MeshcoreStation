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
    assert room_iframe.src=='about:blank'
    assert room_iframe.to_plotly_json()['props']['data-src']=='/rooms?embedded=1'
    assert room_iframe.style['height']=='160px'
    order=['command-history-disclosure','repeater-management-disclosure','repeater-optimizer-disclosure','room-server-disclosure']
    assert [ids.index(i) for i in order]==sorted(ids.index(i) for i in order)


def test_repeater_management_telemetry_and_independent_optimizer_subsections():
    nodes=list(walk(build_layout()))
    management=next(n for n in nodes if getattr(n,'id',None)=='repeater-management-disclosure')
    ids=[getattr(n,'id',None) for n in walk(management)]
    assert not getattr(management, 'open', False)
    assert ids.index('managed-repeater') < ids.index('battery-overview')
    assert 'repeater-statistics-inline' not in ids
    optimizer=next(n for n in nodes if getattr(n,'id',None)=='repeater-optimizer-disclosure')
    children=[n.id for n in optimizer.children if isinstance(n,html.Details)]
    assert children==['repeater-statistics-disclosure','optimization-analysis-disclosure','repeater-network-disclosure']
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


def test_optimizer_subsections_use_one_shared_gutter_without_double_padding():
    nodes=list(walk(build_layout()))
    for key in ('repeater-statistics-disclosure','optimization-analysis-disclosure','repeater-network-disclosure'):
        section=next(n for n in nodes if getattr(n,'id',None)==key)
        assert len(section.children)==2
        assert section.children[1].className=='optimizer-section-body'


def test_network_monitoring_has_no_obsolete_experimental_status():
    nodes=list(walk(build_layout()))
    section=next(n for n in nodes if getattr(n,'id',None)=='repeater-network-disclosure')
    assert section.children[0].children.children == 'Repeater Network Monitoring'
    text=str(section.to_plotly_json())
    assert 'Experimental' not in text
    assert 'unverified' not in text
    assert 'External access may be restricted' in text
