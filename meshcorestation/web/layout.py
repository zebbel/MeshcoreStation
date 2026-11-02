"""V5 milestone layout: three cards, Bot with two subsections, Repeater Management."""
from dash import dcc,html
from meshcorestation.web.data import PAGE_SIZE


def popup(children,**attributes):
    return html.Dialog([children[0],html.Div(children[1:],className='dialog-body')],**attributes)


def build_layout():
    latest_command='No commands yet';latest_detail='Waiting for the first saved command'
    history=html.Section([html.Details([html.Summary([html.H2('Command history'), html.Div([html.P('Last command received', className='eyebrow'), html.Div(latest_command, id='last-command', className='history-latest-command'), html.P(latest_detail, id='last-detail', className='muted')], className='history-latest'), html.Button('Commands', id='open-commands-history', className='info-button', type='button')], className='command-history-summary'), html.Div([html.Div([html.P('Oldest to newest · Europe/Berlin', className='muted', id='history-zone')]), html.Div([html.Label('Command', htmlFor='command-filter'), dcc.Dropdown(id='command-filter', options=[], placeholder='All commands', clearable=True, className='command-filter')], className='filter')], className='toolbar'), html.Div([html.Button('Load older', id='load-older', n_clicks=0, className='secondary'), html.Span(id='row-count', className='muted'), html.Button('↓ Latest', id='jump-latest', className='secondary')], className='list-tools'), html.Div(html.Table([html.Thead(html.Tr([html.Th('Date & time'), html.Th('Command'), html.Th('Received from'), html.Th('Details')])), html.Tbody(id='command-rows')]), id='command-scroll', tabIndex=0, **{'aria-label': 'Command history, oldest first'}), html.Div(id='updated', className='updated muted')], id='command-history-disclosure', className='panel-disclosure')], className='history')
    management=html.Section(html.Details([html.Summary(html.H2('Repeater management')), html.Div([html.Label([html.Span('Selected repeater'), html.Select(id='managed-repeater', **{'aria-label': 'Selected repeater'})]), html.Div([html.Button('Add repeater from map', id='managed-repeater-add', type='button', className='info-button'), html.Button('Open repeater management', id='managed-repeater-open', type='button', className='info-button', disabled=True), html.Button('Remove repeater', id='managed-repeater-remove', type='button', className='info-button', disabled=True)], className='managed-repeater-actions')], className='managed-repeater-controls'), html.P(id='managed-repeater-message', role='status'), html.Section([html.Div([html.H2('Repeater telemetry'), html.Button('Telemetry history / settings', id='open-voltage', className='info-button')], className='toolbar'), html.Div(id='battery-overview')], className='managed-repeater-section')], id='repeater-management-disclosure', className='panel-disclosure'), className='history')
    bot_settings=html.Details([
        html.Summary(html.H2('Bot Settings')),
        html.Div([
            html.H3(id='bot-runtime-status'),html.P(id='bot-channel-status',className='muted'),
            html.P('Replies use the original channel and scope. Commands execute once. Forwarding observations are not receiver delivery confirmation.',className='muted'),
            html.Button('Commands',id='open-commands',className='info-button',type='button'),
            html.Div(id='bot-scopes-host',className='companion-grid')
        ],className='v5-section-body')
    ],id='bot-settings-disclosure',className='panel-disclosure v5-subsection')
    return html.Main([
        html.Header([
            html.Div([html.Div([html.Img(src='/assets/meshcore-logo.png?v=1.2',id='meshcore-brand-image',alt='MeshCore'),html.Span('M',id='brand-fallback',hidden=True)],className='mark meshcore-mark'),html.Div([html.H1('MeshcoreStation'),html.P('Your mesh, at a glance.',className='muted')])],className='brand'),
            html.Div([html.Span(className='live-dot'),' Refreshes every 5 seconds'],className='refresh-label')
        ]),
        html.Div([
            html.Section([html.P('MeshcoreStation',className='eyebrow'),html.H2('MeshcoreStation',className='metric'),html.P('Application preferences, date and time display, and software updates.',className='muted'),html.Button('Settings',id='open-station-settings',className='info-button',type='button')],className='card v5-card',id='station-card'),
            html.Section([html.P('Connected Companion',className='eyebrow'),html.Div('Disconnected',id='bot-status',className='metric unknown'),html.P('Connect your Companion in Settings.',id='bot-detail',className='muted'),html.Div([html.Button('Settings',id='open-companion',className='info-button',type='button'),html.Button('Contacts',id='open-contacts',className='info-button',type='button'),html.Button('Channels',id='open-channels',className='info-button',type='button')],className='v5-card-actions')],className='card v5-card',id='companion-card'),
            html.Section([html.P('Known Repeaters',className='eyebrow'),html.Div('0',id='repeater-count',className='metric'),html.P('Saved locally and available even when the Companion disconnects.',id='repeater-detail',className='muted'),html.Button('Open Map',id='open-repeaters',className='info-button',type='button')],className='card v5-card',id='known-card')
        ],className='cards'),html.Div(id='error',role='status'),
        html.Section(html.Details([html.Summary(html.H2('Bot')),html.Div([bot_settings,history.children[0]],className='v5-section-body')],id='bot-disclosure',className='panel-disclosure'),className='history'),
        management,
        html.Dialog([html.Div([html.H2('MeshcoreStation Settings'),html.Button('×',id='close-station-settings',type='button',**{'aria-label':'Close MeshcoreStation Settings'})],className='dialog-header'),html.Div(className='dialog-body')],id='station-settings-dialog'),
        popup([html.Div([html.Div([html.P('COMMAND DETAILS', className='eyebrow'), html.H2('Received command', id='detail-title')]), html.Button('×', id='close-details', **{'aria-label': 'Close details'})], className='dialog-header'), html.P('Reply text is recorded by the bot; it is not proof of delivery.', className='muted'), html.Section([html.H3('Packet route'), html.Div(id='route-summary', className='route-summary', **{'aria-live': 'polite'}), html.Div(id='route-paths', className='route-paths', role='group', **{'aria-label': 'Reception paths'}), html.Div(id='route-map', className='map-canvas', role='region', **{'aria-label': 'Packet route map'}), html.Div(id='route-notes', className='map-notes')], id='route-section', hidden=True), html.Dl(id='detail-fields')], id='details-dialog', **{'aria-labelledby': 'detail-title'}),
        popup([html.Div([html.H2('Known repeaters', id='repeaters-title'), html.Button('×', id='close-repeaters', **{'aria-label': 'Close repeater map'})], className='dialog-header'), html.Div(id='repeater-notes', className='map-notes', **{'aria-live': 'polite'}), html.Div(id='repeater-map', className='map-canvas', role='region', **{'aria-label': 'Known repeaters map'})], id='repeaters-dialog', **{'aria-labelledby': 'repeaters-title'}),
        html.Footer([html.Span(id='footer-copyright'),html.Span('MeshcoreStation 5.0.0 · V5',id='footer-version'),html.Span('Companion firmware unavailable',id='footer-firmware'),html.Span('Checking for updates…',id='footer-update',role='status',**{'aria-live':'polite'}),html.Button('Update available',id='footer-update-button',hidden=True,type='button')],id='dashboard-footer'),
        dcc.Interval(id='refresh',interval=5000),dcc.Interval(id='history-refresh',interval=5000,disabled=True),dcc.Store(id='window-size',data=PAGE_SIZE),dcc.Store(id='last-render',data=None),dcc.Store(id='history-visible',data=False)
    ],className='shell')
