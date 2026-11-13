"""Browser-specific translations for the dashboard and same-origin tools."""
import json
from functools import lru_cache
from pathlib import Path

from flask import Response, has_request_context, request

CATALOG_DIR = Path(__file__).with_name('locales')
PREFERENCE = 'meshcorestation-language'


@lru_cache(maxsize=1)
def catalogs():
    return {
        file.stem: json.loads(file.read_text(encoding='utf-8'))
        for file in sorted(CATALOG_DIR.glob('*.json'))
    }


def language():
    if has_request_context():
        code = request.cookies.get(PREFERENCE, 'en')
        if code in catalogs():
            return code
    return 'en'


def t(identifier, *values):
    available = catalogs()
    message = available[language()].get(identifier) or available['en'].get(identifier, identifier)
    return message.format(*values) if values else message


def register_localization(server):
    @server.get('/dashboard-locales.js')
    def browser_catalogs():
        source = 'window.MeshcoreStationCatalogs = ' + json.dumps(catalogs(), ensure_ascii=True) + ';'
        return Response(source, mimetype='application/javascript', headers={'Cache-Control': 'no-cache'})

    @server.after_request
    def dashboard_language(response):
        localized = response.mimetype == 'text/html' or request.path.endswith('/_dash-layout')
        if localized and not response.direct_passthrough:
            response.headers['Content-Language'] = language()
            response.vary.add('Cookie')
            response.headers['Cache-Control'] = 'private, no-store'
        return response
