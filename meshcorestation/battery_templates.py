"""Battery report placeholders use the same explicit language as Edit Command."""
from datetime import datetime
from zoneinfo import ZoneInfo
from meshcorestation.commands import templates
from meshcorestation.commands.context import percent as battery_percent

DEFAULT = 'Battery {repeater_name}: {reading} | {sample_time}'
CATALOG = {
    'repeater_name': ('Repeater name', 'Hill repeater'),
    'repeater_public_key': ('Repeater public key', 'ab'*32),
    'battery_voltage': ('Last read voltage, without V', 3.86),
    'battery_percent': ('Approximate 1S LiPo charge, without %', 52),
    'reading': ('Last read voltage with unit', '3.86 V'),
    'sample_time': ('Reading time, DD.MM HH:MM, in report timezone', '22.10 08:00'),
    'date': ('Reading date in report timezone', '22.10.2026'),
    'time': ('Reading time in report timezone', '08:00:00'),
    'timezone': ('Report timezone', 'Europe/Berlin'),
}


def validate(value):
    # Share brace parsing, control character checks, numeric format validation,
    # length limits and non-recursive rendering with the command editor.
    aliases = {'repeater_name':'sender_name', 'repeater_public_key':'sender_public_key',
               'reading':'result', 'sample_time':'uptime', 'timezone':'scope_name'}
    import string
    if not isinstance(value,str) or not value.strip() or len(value.encode('utf-8'))>512:
        raise ValueError('Enter a battery report template of 1–512 UTF-8 bytes.')
    if '\n' in value or '\r' in value:
        raise ValueError('Battery reports must use one line.')
    try:
        parts=list(string.Formatter().parse(value))
    except ValueError:
        raise ValueError('Unmatched braces. Use {{ and }} for literal braces.') from None
    for _,name,_,_ in parts:
        if name is not None and name not in CATALOG:
            raise ValueError('Unknown battery placeholder: {'+name+'}')
    # Map only actual fields, preserving escaped literal braces.
    converted=''.join(literal.replace('{','{{').replace('}','}}') +
        (('{' + aliases.get(name,name) + ((':'+spec) if spec else '') + (('!'+conversion) if conversion else '') + '}') if name is not None else '')
        for literal,name,spec,conversion in parts)
    templates.fields(converted)
    return converted


def render(value, sample, cfg):
    converted=validate(value)
    stamp=datetime.fromtimestamp(sample['sampled_at'],ZoneInfo(cfg['timezone']))
    name=''.join(ch for ch in sample['name'] if ord(ch)>=32 and ord(ch)!=127)
    name=name.encode('utf-8')[:31].decode('utf-8',errors='ignore')
    voltage=sample.get('voltage')
    return templates.render(converted,{
        'sender_name':name, 'sender_public_key':cfg['public_key'],
        'battery_voltage':voltage, 'battery_percent':battery_percent(voltage),
        'result':f'{voltage:.2f} V' if voltage is not None else 'unavailable (no valid reading)',
        'uptime':stamp.strftime('%d.%m %H:%M'), 'date':stamp.strftime('%d.%m.%Y'),
        'time':stamp.strftime('%H:%M:%S'), 'scope_name':cfg['timezone']})


def catalog():
    return [{'name':name,'description':description,'numeric':name in ('battery_voltage','battery_percent')}
            for name,(description,_) in CATALOG.items()]


def preview(value):
    # Render via exactly the same validation/expansion as the scheduled worker.
    return render(value,{'sampled_at':1792648800,'name':'Hill repeater','voltage':3.86},
                  {'timezone':'Europe/Berlin','public_key':'ab'*32})
