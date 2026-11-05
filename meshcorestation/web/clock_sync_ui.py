"""Clock settings share the managed-repeater selection; status is entirely local."""
from dash import html
from meshcorestation.storage.clock_sync import INTERVALS


def clock_sync_panel():
    return html.Details([
        html.Summary([html.Strong('Automatic Clock Synchronization'), html.Span('Disabled by default',id='clock-sync-summary',className='muted')]),
        html.Div([
            html.P('Uses the Companion’s administrator ACL permissions. Only forward corrections are allowed; host NTP synchronization must be confirmed. No passwords are stored.',className='muted'),
            html.Div(id='clock-sync-enable-host'),
            html.Label([html.Span('Synchronization interval'),html.Select([html.Option(f'{hours} hours',value=str(hours),selected=hours==24) for hours in INTERVALS],id='clock-sync-interval')]),
            html.Button('Save settings',id='clock-sync-save',type='button',className='info-button',disabled=True),
            html.P(id='clock-sync-message',role='status'),
            html.Dl([item for label,identifier in [('Current feature status','state'),('Last synchronization attempt','attempt'),('Last attempt result','result'),('Last successful synchronization / verification','success'),('Next scheduled synchronization','next'),('Last measured clock difference (repeater − host)','offset'),('Last error','error')] for item in [html.Dt(label),html.Dd('Not recorded',id='clock-sync-'+identifier)]],className='clock-sync-status'),
        ],className='v5-section-body clock-sync-body'),
    ],id='clock-sync-disclosure',className='panel-disclosure v5-subsection')
