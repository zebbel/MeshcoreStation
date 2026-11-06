"""V5 milestone layout: three cards, Bot with two subsections, Repeater Management."""
from dash import dcc,html
from meshcorestation.web.clock_sync_ui import clock_sync_panel
from meshcorestation.web.data import PAGE_SIZE


def popup(children,**attributes):
    return html.Dialog([children[0],html.Div(children[1:],className='dialog-body')],**attributes)


def statistics_panel(title,key,children):
    return html.Details([html.Summary(html.H3(title)),html.Div(children,className='statistics-panel-body')],
                        id='statistics-'+key+'-section',className='statistics-block statistics-accordion')


def build_layout():
    latest_command='No commands yet';latest_detail='Waiting for the first saved command'
    history=html.Section([html.Details([html.Summary([html.H2('Command history'), html.Div([html.P('Last command received', className='eyebrow'), html.Div(latest_command, id='last-command', className='history-latest-command'), html.P(latest_detail, id='last-detail', className='muted')], className='history-latest'), html.Button('Commands', id='open-commands-history', className='info-button', type='button')], className='command-history-summary'), html.Div([html.Div([html.P('Oldest to newest · Europe/Berlin', className='muted', id='history-zone')]), html.Div([html.Label('Command', htmlFor='command-filter'), dcc.Dropdown(id='command-filter', options=[], placeholder='All commands', clearable=True, className='command-filter')], className='filter')], className='toolbar'), html.Div([html.Button('Load older', id='load-older', n_clicks=0, className='secondary'), html.Span(id='row-count', className='muted'), html.Button('↓ Latest', id='jump-latest', className='secondary')], className='list-tools'), html.Div(html.Table([html.Thead(html.Tr([html.Th('Date & time'), html.Th('Command'), html.Th('Received from'), html.Th('Details')])), html.Tbody(id='command-rows')]), id='command-scroll', tabIndex=0, **{'aria-label': 'Command history, oldest first'}), html.Div(id='updated', className='updated muted')], id='command-history-disclosure', className='panel-disclosure')], className='history')
    management=html.Section(html.Details([html.Summary(html.H2('Repeater management')), html.Div([html.Label([html.Span('Selected repeater'), html.Select(id='managed-repeater', **{'aria-label': 'Selected repeater'})]), html.Div([html.Button('Add repeater from map', id='managed-repeater-add', type='button', className='info-button'), html.Button('Open repeater management', id='managed-repeater-open', type='button', className='info-button', disabled=True), html.Button('Remove repeater', id='managed-repeater-remove', type='button', className='info-button', disabled=True)], className='managed-repeater-actions')], className='managed-repeater-controls'), html.P(id='managed-repeater-message', role='status'), clock_sync_panel(), html.Section([html.Div([html.H2('Repeater telemetry'), html.Button('Telemetry history / settings', id='open-voltage', className='info-button')], className='toolbar'), html.Div(id='battery-overview')], className='managed-repeater-section')], id='repeater-management-disclosure', className='panel-disclosure'), className='history')
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
        html.Section(html.Details([
            html.Summary(html.H2('Room Server')),
            html.Div(html.Iframe(id='room-server-frame',title='Room Server administration',style={'height':'120px'}, **{'data-src':'/rooms?embedded=1'}),className='v5-section-body room-server-inline')
        ],id='room-server-disclosure',className='panel-disclosure'),className='history'),
        management,
        html.Section(html.Details([
            html.Summary(html.H2('Repeater Statistics')),
            html.Div([
                html.Div([html.Label(['Viewed Repeater',html.Select(id='statistics-repeater',**{'aria-label':'Statistics repeater'})]),
                    html.Label(['Observation period',html.Select([html.Option('24 hours',value='1'),html.Option('7 days',value='7'),html.Option('30 days',value='30')],id='statistics-period')]),
                    html.Button('Refresh saved view',id='statistics-refresh',type='button',className='info-button')
                ],className='statistics-controls'),
                html.Details([html.Summary(['Automatic neighbor SNR monitoring · ',html.Span(id='neighbor-monitor-summary')]),html.Fieldset([
                    html.Legend('Automatic neighbor SNR monitoring'),
                    html.Label([html.Span(id='neighbor-monitor-checkbox-host'), ' Enable for this repeater']),
                    html.Label(['Interval (minutes)',dcc.Input(id='neighbor-monitor-interval',type='number',min=5,max=1440,step=1,value=30)]),
                    html.Button('Save monitoring settings',id='neighbor-monitor-save',type='button',className='info-button'),
                    html.P('Disabled by default. Enabling sends paced read-only guest neighbor requests even while this dashboard is closed. Passive recording is independent.',className='muted'),
                    html.P(id='neighbor-monitor-status',role='status'),
                    html.Button('Recheck SNR protocol at next collection',id='neighbor-monitor-recheck',type='button',className='info-button'),
                    html.Div(id='neighbor-monitor-protocol-details',className='statistics-monitor-details')
                ],id='neighbor-monitor-settings',className='statistics-controls',disabled=True)],id='neighbor-monitor-disclosure'),
                html.P(id='statistics-status' ,role='status',**{'aria-live':'polite'}),
                html.P(id='statistics-error',role='alert'),
                html.P(id='statistics-view-status',role='status',**{'aria-live':'polite'}),
                html.P(id='statistics-view-error',role='alert'),
                html.P('Recorded collection coverage: Unavailable',id='statistics-coverage-summary',className='muted'),html.Details([html.Summary('Recording Details'),html.P('Passive recording and scheduled SNR monitoring are independent.'),html.P(id='statistics-coverage',className='muted')],id='statistics-recording-details'),
                statistics_panel('Observed Neighbor Map','map',[html.Label([html.Span(id='statistics-one-way-host'),' Show one-way connections']),html.Div(id='statistics-map-notes'),html.Div(id='statistics-neighbor-map',className='map-canvas',role='region',**{'aria-label':'Observed Neighbor Map'}),html.H4('Neighbors without coordinates'),html.Ul(id='statistics-missing-coordinates'),html.Details([html.Summary('Ambiguous connections'),html.Ul(id='statistics-ambiguous')])]),
                statistics_panel('Most Active Neighbors','active',[html.Div(id='statistics-active-neighbors',className='statistics-chart')]),
                statistics_panel('Traffic Activity Heatmap','activity',[html.Div(id='statistics-heatmap',className='statistics-chart')]),
                statistics_panel('Packet Type Distribution','types',[html.Div(id='statistics-packet-types',className='statistics-chart')]),
                statistics_panel('Messages per Hour','messages',[html.Div(id='statistics-hourly',className='statistics-chart')]),
                statistics_panel('Hop Count Ranking','hops',[html.P('Ordered by total observed flood-route hop count. Side-by-side columns show unique and repeated receptions; the exact-count table retains unidentified receptions.',className='muted'),html.Div(id='statistics-hops',className='statistics-chart')]),
                statistics_panel('MeshCore Regional Traffic Ranking','regions',[html.P('Unscoped is ranked alongside named regions. Unknown means a scoped packet could not be matched uniquely to a configured key.',className='muted'),html.Div(id='statistics-regions',className='statistics-chart'),html.Details([html.Summary('Configure known region names'),html.P('One region name per line; append an optional 32-hex custom scope key after a space. Otherwise the MeshCore hashtag key is derived. Existing Bot reply scopes are also checked. This saves local display attribution only; it sends no radio commands.'),html.Textarea(id='statistics-region-names',rows=5,**{'aria-label':'Known region names and optional scope keys'}),html.Button('Save region names',id='statistics-regions-save',type='button',className='info-button'),html.P(id='statistics-region-status',role='status')],id='statistics-regions-settings')]),
                statistics_panel('Neighbor SNR — Average','snr',[html.P('Repeater-side SNR observations, not packet-delivery rates. Firmware aggregates use actual sample counts; legacy last-heard monitoring deduplicates repeated polling. Sources remain distinct.',className='muted'),html.Div(id='statistics-neighbor-snr')]),

                html.P('Route hashes can be ambiguous. Recorded routes do not prove receiver delivery or verified direct radio links.',className='muted')
            ],className='v5-section-body')
        ],id='repeater-statistics-disclosure',className='panel-disclosure'),className='history'),
        html.Section(html.Details([
            html.Summary(html.H2('Repeater Statistic Comparison')),
            html.Div([
                html.Div([html.Label(['Viewed Repeater',html.Select(id='comparison-repeater')]),html.Button('Refresh changes',id='comparison-refresh',type='button',className='secondary')],className='statistics-controls'),
                html.Label(['Change Description',dcc.Input(id='comparison-description',type='text',maxLength=500,placeholder='Describe the repeater change')]),
                html.Button('Save Change',id='comparison-save',type='button',className='info-button'),
                html.P('The server records the current time when saved. Logging a change sends no repeater command.',className='muted'),
                html.P(id='comparison-status',role='status'),html.P(id='comparison-error',role='alert'),
                html.Div(id='comparison-journal',className='statistics-table-scroll'),
                html.Button('Load more changes',id='comparison-more',type='button',className='secondary',hidden=True),
                html.Div([html.Label(['Saved Change',html.Select(id='comparison-change')]),html.Label(['Comparison Period',html.Select([html.Option('24 hours',value='1'),html.Option('7 days',value='7'),html.Option('30 days',value='30')],id='comparison-period')]),html.Button('Compare saved history',id='comparison-run',type='button',className='info-button')],className='statistics-controls'),
                html.Div(id='comparison-results',**{'aria-live':'polite'})
            ],className='v5-section-body')
        ],id='repeater-comparison-disclosure',className='panel-disclosure'),className='history'),
        html.Dialog([html.Div([html.H2('MeshcoreStation Settings'),html.Button('×',id='close-station-settings',type='button',**{'aria-label':'Close MeshcoreStation Settings'})],className='dialog-header'),html.Div(className='dialog-body')],id='station-settings-dialog'),
        popup([html.Div([html.Div([html.P('COMMAND DETAILS', className='eyebrow'), html.H2('Received command', id='detail-title')]), html.Button('×', id='close-details', **{'aria-label': 'Close details'})], className='dialog-header'), html.P('Reply text is recorded by the bot; it is not proof of delivery.', className='muted'), html.Section([html.H3('Packet route'), html.Div(id='route-summary', className='route-summary', **{'aria-live': 'polite'}), html.Div(id='route-paths', className='route-paths', role='group', **{'aria-label': 'Reception paths'}), html.Div(id='route-map', className='map-canvas', role='region', **{'aria-label': 'Packet route map'}), html.Div(id='route-notes', className='map-notes')], id='route-section', hidden=True), html.Dl(id='detail-fields')], id='details-dialog', **{'aria-labelledby': 'detail-title'}),
        popup([html.Div([html.H2('Known repeaters', id='repeaters-title'), html.Button('×', id='close-repeaters', **{'aria-label': 'Close repeater map'})], className='dialog-header'), html.Div(id='repeater-notes', className='map-notes', **{'aria-live': 'polite'}), html.Div(id='repeater-map', className='map-canvas', role='region', **{'aria-label': 'Known repeaters map'})], id='repeaters-dialog', **{'aria-labelledby': 'repeaters-title'}),
        html.Footer([html.Span(id='footer-copyright'),html.Span('MeshcoreStation 5.8.0 · V5',id='footer-version'),html.Span('Companion firmware unavailable',id='footer-firmware'),html.Span('Checking for updates…',id='footer-update',role='status',**{'aria-live':'polite'}),html.Button('Update available',id='footer-update-button',hidden=True,type='button')],id='dashboard-footer'),
        dcc.Interval(id='refresh',interval=5000),dcc.Interval(id='history-refresh',interval=5000,disabled=True),dcc.Store(id='window-size',data=PAGE_SIZE),dcc.Store(id='last-render',data=None),dcc.Store(id='history-visible',data=False)
    ],className='shell')
