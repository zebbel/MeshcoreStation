"""Shared advisor reference schema and deterministic, evidence-qualified review."""
import time
from meshcorestation.radio.repeater_fields import FIELDS, validate as validate_field

TARGETS = {'flood.max':16, 'flood.max.unscoped':3, 'flood.max.advert':6,
           'advert.interval':240, 'flood.advert.interval':48, 'loop.detect':'minimal'}
DEFAULT = {'targets':TARGETS, 'min_copies':100, 'min_days':7,
           'enabled':{key:True for key in TARGETS}}
SOURCE = {'url':'https://github.com/meshcore-dev/MeshCore/blob/main/docs/cli_commands.md',
          'checked':'2026-10-17', 'status':'Command semantics checked; inherited numerical references are provisional, not verified German community consensus.'}


def validate(data):
    if not isinstance(data,dict) or set(data) != set(DEFAULT):
        raise ValueError('Invalid advisor configuration.')
    for name in ('targets','enabled'):
        if not isinstance(data[name],dict) or set(data[name]) != set(TARGETS):
            raise ValueError('Invalid advisor fields.')
    for field in TARGETS:
        if type(data['enabled'][field]) is not bool:
            raise ValueError('Invalid enabled flag.')
        validate_field(field,data['targets'][field])
    if type(data['min_copies']) is not int or not 0 <= data['min_copies'] <= 100000:
        raise ValueError('Invalid minimum copies.')
    if type(data['min_days']) is not int or data['min_days'] not in (1,7,30):
        raise ValueError('Invalid observation period.')
    return data


def schema():
    return {key:{**FIELDS[key], 'reference':TARGETS[key], 'source':SOURCE} for key in TARGETS}


def review(current, settings, snapshot, public_key, now=None):
    now = time.time() if now is None else now
    health = snapshot.get('health') or {}
    selection = snapshot.get('selection') or {}
    reasons = []
    if not public_key or public_key != selection.get('public_key'): reasons.append('Statistics belong to a different or unselected repeater.')
    if snapshot.get('days') != settings['min_days']: reasons.append('Observation period does not match.')
    if snapshot.get('copies',0) < settings['min_copies']: reasons.append('Too few observed copies.')
    if selection.get('since',now) > now-settings['min_days']*86400 or snapshot.get('usefulness',{}).get('partial',True): reasons.append('Observation window is incomplete.')
    if health.get('dropped'): reasons.append('Collector dropped observations.')
    if health.get('trimmed_at'): reasons.append('Observation history was truncated.')
    if not health.get('running') or now-(health.get('heartbeat') or 0)>60: reasons.append('Collector is inactive or stale.')
    if health.get('error'): reasons.append('Collector reports an error.')
    if health.get('radio') != 'Running': reasons.append('Companion radio is not connected.')
    rows=[]
    for field,target in settings['targets'].items():
        if not settings['enabled'][field]: continue
        value=current.get(field)
        try:
            normalized=validate_field(field,value)
            target_value=validate_field(field,target)
            status='Matches reference' if normalized==target_value else 'Manual review'
            can_apply=normalized!=target_value
        except (ValueError,TypeError):
            status='Not evaluated';can_apply=False
        rows.append({'field':field,'current':value,'reference':target,'status':status,'can_apply':can_apply,
                     'explanation':'Reference comparison only. Confirm local topology and scope requirements before changing settings.'})
    return {'rows':rows,'evidence_reasons':reasons,'confidence':'insufficient observations' if reasons else 'limited local observations',
            'evidence':snapshot.get('evidence',{}),'source':SOURCE}
