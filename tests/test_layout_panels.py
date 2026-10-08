from meshcorestation.web.layout import build_layout


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
