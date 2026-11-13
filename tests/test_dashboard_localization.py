import re

from flask import Flask

from meshcorestation.web.i18n import catalogs, register_localization, t
from meshcorestation.web.layout import build_layout


def test_request_languages_are_independent_and_unknown_languages_fall_back():
    server = Flask(__name__)
    register_localization(server)
    server.get('/example')(lambda: t('Details for command {0}', 42))
    english = server.test_client()
    german = server.test_client()
    german.set_cookie('meshcorestation-language', 'de')
    response = german.get('/example')
    assert response.text == 'Details zu Befehl 42'
    assert response.headers['Content-Language'] == 'de'
    assert 'Cookie' in response.vary
    assert english.get('/example').text == 'Details for command 42'
    english.set_cookie('meshcorestation-language', 'unsupported')
    assert english.get('/example').headers['Content-Language'] == 'en'


def test_dash_layout_keeps_ids_and_options_in_both_languages():
    def inspect(value, components, strings):
        if hasattr(value, 'to_plotly_json'):
            value = value.to_plotly_json()['props']
            if 'id' in value:
                components[value['id']] = value
        if isinstance(value, dict):
            for item in value.values():
                inspect(item, components, strings)
        elif isinstance(value, (list, tuple)):
            for item in value:
                inspect(item, components, strings)
        elif isinstance(value, str):
            strings.add(value)

    server = Flask(__name__)
    outputs = []
    for code in ('en', 'de'):
        with server.test_request_context(headers={'Cookie': f'meshcorestation-language={code}'}):
            components, strings = {}, set()
            inspect(build_layout(), components, strings)
            outputs.append((components, strings))
    (en, en_strings), (de, de_strings) = outputs
    assert en.keys() == de.keys()
    assert 'Repeater Statistics' in en_strings
    assert 'Repeater-Statistiken' in de_strings
    for components in (en, de):
        assert [c.value for c in components['statistics-period']['children']] == ['1', '7', '30']
        assert [c.value for c in components['dashboard-language']['children']] == ['en', 'de']
    assert de['dashboard-language']['children'][1].selected


def test_catalog_placeholders_and_english_fallback(monkeypatch):
    server = Flask(__name__)
    available = catalogs()
    assert available['de'].keys() <= available['en'].keys()
    for identifier, translated in available['de'].items():
        assert set(re.findall(r'\{\d+\}', translated)) == set(re.findall(r'\{\d+\}', available['en'][identifier]))
    monkeypatch.delitem(available['de'], 'Details for command {0}')
    with server.test_request_context(headers={'Cookie': 'meshcorestation-language=de'}):
        assert t('Details for command {0}', 42) == 'Details for command 42'
        assert t('Untranslated text') == 'Untranslated text'
