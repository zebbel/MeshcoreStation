"""Application-wide display controls, also bootstrapped into standalone pages."""
import html
import json
from flask import request
from meshcorestation import display
from meshcorestation.config import TIMEZONE
from meshcorestation.web.http import control_request_error, json_response


def register_display_routes(server):
    @server.route('/api/display-settings', methods=['GET', 'POST'])
    def preferences():
        if control_request_error():
            return json_response({'ok':False, 'error':'Open from the local dashboard.'},403)
        try:
            if request.method == 'POST':
                if request.mimetype != 'application/json' or (request.content_length or 0)>1024:
                    raise ValueError('Expected display settings JSON.')
                value = display.save(request.get_json())
            else:
                value = display.settings()
            return json_response({'ok':True, 'settings':value, 'timezone':TIMEZONE.key})
        except (TypeError, ValueError) as error:
            return json_response({'ok':False,'error':str(error)},400)
        except OSError:
            return json_response({'ok':False,'error':'Could not save display settings.'},503)

    @server.after_request
    def bootstrap(response):
        if response.mimetype == 'text/html' and not response.direct_passthrough:
            content = response.get_data(as_text=True)
            if '</head>' in content:
                value = {**display.settings(), 'timezone':TIMEZONE.key}
                meta = '<meta name="meshcorestation-display" content="' + html.escape(json.dumps(value),quote=True) + '">'
                # Dash includes the same asset itself. Other HTML tools and
                # embedded pages need the formatter before their inline scripts.
                script = '' if 'aa_display.js' in content else '<script src="/assets/aa_display.js"></script>'
                response.set_data(content.replace('</head>',meta+script+'</head>',1))
                response.headers['Cache-Control'] = 'no-store'
        return response
