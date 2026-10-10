"""Validated OLED documents and a bounded, named database source catalog."""
import hashlib
import json
import math
import time

VALUES = {
    'battery.name': 'Selected battery repeater', 'battery.voltage': 'Battery voltage',
    'battery.percent': 'Battery percent', 'repeaters.count': 'Known repeaters',
    'commands.count': 'Received command count',
    'battery.age_minutes': 'Battery reading age (minutes)',
    'battery.status': 'Battery reading status',
    'battery.sample_time': 'Battery reading time',
}
for n in range(1, 4):
    for field in ('sender', 'message', 'time', 'rssi', 'snr', 'path_len'):
        VALUES[f'command{n}.{field}'] = f'Command {n}: {field}'
SERIES = {'battery.voltage': 'Battery voltage', 'battery.percent': 'Battery percent',
          'commands.rssi': 'Command RSSI', 'commands.snr': 'Command SNR',
          'commands.path_len': 'Command hop count'}


def element(kind, x, y, w, h, **extra):
    return dict(kind=kind, x=x, y=y, w=w, h=h, **extra)


def defaults():
    battery = [
        element('value', 0, 0, 128, 8, source='battery.name', size=1, label='', units='', precision=0),
        element('value', 0, 10, 72, 8, source='battery.voltage', size=1, label='', units='V', precision=2),
        element('value', 78, 10, 48, 8, source='battery.percent', size=1, label='~', units='%', precision=0),
        element('graph', 0, 24, 128, 30, source='battery.voltage', hours=24, minimum=3.0, maximum=4.2),
        element('text', 0, 56, 102, 8, text='24h 3.0-4.2V', size=1),
        element('text', 108, 56, 18, 8, text='now', size=1),
    ]
    commands = [element('text', 0, 0, 128, 8, text='Last commands', size=1)]
    for n in range(1, 4):
        y = 8 + (n-1)*16
        commands += [
            element('value', 0, y, 36, 8, source=f'command{n}.time', size=1, label='', units='', precision=0),
            element('value', 36, y, 90, 8, source=f'command{n}.sender', size=1, label='', units='', precision=0),
            element('value', 0, y+8, 128, 8, source=f'command{n}.message', size=1, label='', units='', precision=0)]
    return [dict(name='Battery', enabled=True, elements=battery),
            dict(name='Commands', enabled=True, elements=commands)]


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS oled_pages (id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL, preview TEXT, preview_until REAL NOT NULL DEFAULT 0)')
    db.execute('INSERT OR IGNORE INTO oled_pages (id,document) VALUES (1,?)', (json.dumps(defaults()),))


def snapshot(db):
    document = db.execute('SELECT document FROM oled_pages WHERE id=1').fetchone()[0]
    return dict(ok=True, pages=json.loads(document), revision=hashlib.sha256(document.encode()).hexdigest())


def validate(pages):
    if not isinstance(pages, list) or not 1 <= len(pages) <= 12:
        raise ValueError('Keep between 1 and 12 pages.')
    clean = []
    def integer(v, low, high):
        if type(v) is not int or not low <= v <= high:
            raise ValueError(f'Expected a whole number between {low} and {high}.')
        return v
    def text(v, limit):
        if not isinstance(v, str) or len(v) > limit:
            raise ValueError(f'Text must be at most {limit} characters.')
        return v
    for page in pages:
        if not isinstance(page, dict) or type(page.get('enabled')) is not bool:
            raise ValueError('Invalid page.')
        name = text(page.get('name'), 40).strip()
        if not name:
            raise ValueError('Give each page a name.')
        items = page.get('elements')
        if not isinstance(items, list) or len(items) > 16:
            raise ValueError('Use at most 16 elements per page.')
        result = []
        for e in items:
            if not isinstance(e, dict) or e.get('kind') not in ('text', 'value', 'graph'):
                raise ValueError('Unknown element.')
            kind = e['kind']
            x,y = integer(e.get('x'),0,127),integer(e.get('y'),0,63)
            w,h = integer(e.get('w'),1,128),integer(e.get('h'),1,64)
            if x+w > 128 or y+h > 64:
                raise ValueError('Elements must fit inside 128 x 64 pixels.')
            item = element(kind,x,y,w,h)
            if kind == 'graph':
                if w < 8 or h < 8 or e.get('source') not in SERIES:
                    raise ValueError('Choose a graph series and an area of at least 8 x 8.')
                low,high = e.get('minimum'),e.get('maximum')
                if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e9 for v in (low,high)) or low >= high:
                    raise ValueError('Graph minimum must be lower than maximum.')
                item.update(source=e['source'], minimum=low, maximum=high, hours=integer(e.get('hours'),1,720))
            else:
                size = integer(e.get('size'),1,2)
                if w < 6*size or h < 8*size:
                    raise ValueError('Text area is too small for the selected font size.')
                item['size'] = size
                if kind == 'text':
                    item['text'] = text(e.get('text'),128)
                else:
                    if e.get('source') not in VALUES:
                        raise ValueError('Choose a database value.')
                    item.update(source=e['source'],label=text(e.get('label',''),40),
                                units=text(e.get('units',''),16),precision=integer(e.get('precision',0),0,4))
            result.append(item)
        if sum(e['kind']=='graph' for e in result)>4:
            raise ValueError('Use at most four graphs per page.')
        clean.append(dict(name=name,enabled=page['enabled'],elements=result))
    if not any(p['enabled'] for p in clean):
        raise ValueError('Enable at least one page.')
    return clean


def save(db, pages, revision):
    pages = validate(pages)
    db.execute('BEGIN IMMEDIATE')
    if snapshot(db)['revision'] != revision:
        raise RuntimeError('Pages changed in another window. Reload before saving.')
    db.execute('UPDATE oled_pages SET document=?,preview=NULL,preview_until=0 WHERE id=1', (json.dumps(pages),))
    return snapshot(db)


def active(db, now):
    row = db.execute('SELECT document,preview,preview_until FROM oled_pages WHERE id=1').fetchone()
    if row['preview'] and row['preview_until'] > now:
        return [json.loads(row['preview'])]
    return [p for p in json.loads(row['document']) if p['enabled']]
