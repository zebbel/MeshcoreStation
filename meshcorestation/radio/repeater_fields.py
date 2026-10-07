"""Allowlisted repeater fields: labels, wire commands, parsing and validation."""
import math
import re

# The same schema drives the form and validates every value again on the server.
FIELDS = {
    'name': dict(section='basic', label='Name', kind='text', limit=31),
    'admin_password': dict(section='basic', label='Admin password', kind='password', limit=15, write='password'),
    'guest.password': dict(section='basic', label='Guest password', kind='password', limit=15),
    'radio': dict(section='radio', label='Frequency / bandwidth / SF / CR', kind='radio'),
    'tx': dict(section='radio', label='TX power (dBm)', kind='number', low=-9, high=30, step=1),
    'radio.rxgain': dict(section='radio', label='RX gain boost', kind='select', options=['off', 'on']),
    'lat': dict(section='location', label='Latitude', kind='number', low=-90, high=90),
    'lon': dict(section='location', label='Longitude', kind='number', low=-180, high=180),
    'advert.interval': dict(section='advertisements', label='Local interval (minutes; 0 disables)', kind='number', low=0, high=240, step=2),
    'flood.advert.interval': dict(section='advertisements', label='Flood interval (hours; 0 disables)', kind='number', low=0, high=168, step=1),
    'repeat': dict(section='routing', label='Packet forwarding', kind='select', options=['off', 'on']),
    'flood.max': dict(section='routing', label='Maximum flood hops', kind='number', low=0, high=64, step=1),
    'allow.read.only': dict(section='access', label='Guest access', kind='select', options=['off', 'on']),
    'owner.info': dict(section='owner', label='Owner information', kind='textarea', limit=120),
    'path.hash.mode': dict(section='advanced', label='Path hash size', kind='select', options=['0', '1', '2'], labels=['1 byte', '2 bytes', '3 bytes']),
    'loop.detect': dict(section='advanced', label='Loop detection', kind='select', options=['off', 'minimal', 'moderate', 'strict']),
    'dutycycle': dict(section='advanced', label='Duty cycle limit (%)', kind='number', low=1, high=100),
    'multi.acks': dict(section='advanced', label='Multi-ACKs', kind='number', low=0, high=2, step=1),
    'txdelay': dict(section='advanced', label='Flood TX delay factor', kind='number', low=0, high=2),
    'direct.txdelay': dict(section='advanced', label='Direct TX delay factor', kind='number', low=0, high=2),
    'int.thresh': dict(section='advanced', label='Interference threshold', kind='number', low=0, high=255, step=1),
    'agc.reset.interval': dict(section='advanced', label='AGC reset interval (seconds)', kind='number', low=0, high=240, step=4),
}


def numeric(value, low, high, step=None):
    if isinstance(value, bool):
        raise ValueError('Expected a number.')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError('Expected a number.') from None
    if not math.isfinite(number) or not low <= number <= high or (step and abs(number / step - round(number / step)) > 1e-6):
        raise ValueError(f'Expected {low}–{high}' + (f' in steps of {step}.' if step else '.'))
    return format(number, '.10g')


def validate(field, value):
    spec = FIELDS[field]
    kind = spec['kind']
    if kind == 'radio':
        if not isinstance(value, str) or len(value.split(',')) != 4:
            raise ValueError('Enter frequency, bandwidth, spreading factor and coding rate.')
        freq, bw, sf, cr = value.split(',')
        return ','.join([numeric(freq, 150, 2500), numeric(bw, 7.8, 500), numeric(sf, 5, 12, 1), numeric(cr, 5, 8, 1)])
    if kind == 'number':
        result = numeric(value, spec['low'], spec['high'], spec.get('step'))
        if field == 'advert.interval' and 0 < float(result) < 60:
            raise ValueError('Use 0 or 60–240 minutes, in steps of 2.')
        if field == 'flood.advert.interval' and 0 < float(result) < 3:
            raise ValueError('Use 0 or 3–168 hours.')
        return result
    if not isinstance(value, str):
        raise ValueError('Expected text.')
    if kind == 'select':
        if value not in spec['options']:
            raise ValueError('Invalid selection.')
        return value
    if kind == 'textarea':
        value = value.replace('\n', '|')
    if re.search(r'[\x00-\x1f\x7f]', value) or len(value.encode()) > spec['limit']:
        raise ValueError(f"Use at most {spec['limit']} UTF-8 bytes without control characters.")
    if field in {'name', 'admin_password'} and not value.strip():
        raise ValueError('This value cannot be empty.')
    return value


def parse_value(field, reply):
    if not reply.startswith('>'):
        raise ValueError('Setting is unsupported or its response was not recognized: ' + reply[:160])
    value = reply[1:].strip()
    if field == 'dutycycle':
        value = value.rstrip('%')
    if FIELDS[field]['kind'] == 'number':
        # Read values outside our editing range, without silently changing them.
        if not re.fullmatch(r'-?\d+(?:\.\d+)?', value):
            raise ValueError('Unreadable numeric response.')
        return format(float(value), '.10g')
    return value
