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
    """Explain observed behavior first. References are not automatic recommendations.

    Only offer a *controlled trial* when measurements and valid live settings
    support a plausible intervention; never claim packet copies prove loops or
    observed routes establish the correct flood hop limit.
    """
    now = time.time() if now is None else now
    health = snapshot.get('health') or {}
    selection = snapshot.get('selection') or {}
    evidence = snapshot.get('evidence') or {}
    reasons = []
    matched = bool(public_key and public_key == selection.get('public_key'))
    if not matched:
        reasons.append('Statistics belong to a different or unselected repeater.')
    days = settings['min_days']
    if snapshot.get('days') != days:
        reasons.append('Observation period does not match.')
    copies = snapshot.get('copies') or 0
    if copies < settings['min_copies']:
        reasons.append('Too few observed copies.')
    if selection.get('since', now) > now - days * 86400 or (snapshot.get('usefulness') or {}).get('partial', True):
        reasons.append('Observation window is incomplete.')
    if health.get('dropped'):
        reasons.append('Collector dropped observations.')
    if health.get('trimmed_at'):
        reasons.append('Observation history was truncated.')
    if not health.get('running') or now - (health.get('heartbeat') or 0) > 60:
        reasons.append('Collector is inactive or stale.')
    if health.get('error'):
        reasons.append('Collector reports an error.')
    if health.get('radio') != 'Running':
        reasons.append('Companion radio is not connected.')

    active_days = evidence.get('active_days') or 0
    if copies >= settings['min_copies'] and days >= 7 and 'active_days' in evidence and active_days < 3:
        reasons.append('Observations cover fewer than three active days.')

    recommendations = []
    def suggest(code, title, metric, explanation, action, field=None, proposed=None, confidence='limited'):
        recommendations.append(dict(
            id=code, title=title, evidence=metric, explanation=explanation,
            action=action, field=field, proposed=proposed, confidence=confidence,
            # Candidates require a complete, matching, current baseline.
            can_apply=bool(field and proposed is not None and matched and not reasons),
            kind='trial' if proposed is not None else 'investigation'))

    if reasons:
        suggest('baseline', 'Improve the observation baseline',
                f'{copies} observed copies in {days} day(s).',
                'Analysis may be biased by missing data, inactive collection, or a different repeater.',
                'Select this repeater in statistics, keep the collector online, and gather a complete observation window.',
                confidence='insufficient')

    # Never use another repeater's observations for performance advice.
    if matched and copies:
        identified = evidence.get('identified') or 0
        repeated = evidence.get('repeated') or 0
        route_count = evidence.get('routes') or 0
        adverts = evidence.get('adverts') or 0
        unscoped = evidence.get('unscoped') or 0
        repeat_ratio = repeated / identified if identified else 0
        unscoped_ratio = unscoped / copies
        advert_ratio = adverts / copies

        if identified >= 100 and repeat_ratio >= .30:
            mode = current.get('loop.detect')
            # Official CLI: minimal rejects flood packets that contain
            # repeated repeater hashes. Repeated *digests* aren't loop proof.
            # Offer a reversible experiment only with diverse routes and a
            # healthy, complete observation window; not a claimed optimum.
            if (mode == 'off' and not reasons and copies >= 200 and
                    identified >= 150 and identified / copies >= .70 and
                    route_count >= 2 and active_days >= 3):
                suggest(
                    'loop-trial', 'Consider a minimal loop-detection trial',
                    f'{repeated} of {identified} identified observations repeat a payload digest ({repeat_ratio:.0%}); {route_count} observed routes.',
                    'Repeated content can be legitimate retransmission or multi-path reception. This is NOT proof of a loop. Firmware minimal mode filters certain repeated path hashes; the outcome needs measurement.',
                    'If your network permits, trial off → minimal, then compare similar traffic periods and restore off if reachability degrades.',
                    field='loop.detect', proposed='minimal', confidence='experimental')
            else:
                suggest(
                    'duplicates', 'Investigate repeated payload observations',
                    f'{repeated} of {identified} identifiable observations repeat a payload digest ({repeat_ratio:.0%}).',
                    'The companion sees repeated payloads, which can be normal re-transmissions or alternate routes. No loop or transmission waste is proven.',
                    'Inspect recurring routes, check firmware loop detection and look for direct repeater diagnostics before adjusting a setting.')

        if copies >= 100 and unscoped >= 50 and unscoped_ratio >= .50:
            suggest(
                'unscoped', 'Review unscoped traffic and scope policy',
                f'{unscoped} of {copies} observed copies are unscoped ({unscoped_ratio:.0%}).',
                'A substantial share of observed forwarded traffic lacks region scope. This alone does not establish the correct unscoped flood limit or that traffic is harmful.',
                'Check region configuration and intended reachability. Compare unscoped behavior before considering a manual flood.max.unscoped change.',
                field='flood.max.unscoped')

        if copies >= 100 and adverts >= 40 and advert_ratio >= .30:
            suggest(
                'adverts', 'Review advertisement traffic',
                f'{adverts} of {copies} observed copies are advertisements ({advert_ratio:.0%}).',
                'These are adverts forwarded in paths through the selected repeater, not a count of adverts originating from it. Changing its local advert timer may not reduce them.',
                'Inspect sources and discovery requirements, then consider advert interval changes only with additional diagnostics.',
                field='flood.advert.interval')

        if copies >= 150 and route_count in (1, 2):
            suggest(
                'routes', 'Check path diversity',
                f'{copies} copies appear across {route_count} identifiable route(s).',
                'Few observed routes can be perfectly normal and do not prove poor coverage. Unheard paths are missing from this data.',
                'Compare neighbor discovery and reception from other locations; avoid lowering hop limits based solely on observed route length.')

    if not recommendations:
        suggest('observe', 'No actionable optimization signal in the collected data',
                f'{copies} copies observed over {days} day(s).',
                'The recorded observations do not justify a particular configuration change. This is not proof of optimal repeater performance.',
                'Keep collecting traffic, inspect repeater status/telemetry, and review trends after a comparable observation period.',
                confidence='limited' if not reasons else 'insufficient')

    rows = []
    for field, target in settings['targets'].items():
        if not settings['enabled'][field]:
            continue
        value = current.get(field)
        try:
            normalized = validate_field(field, value)
            target_value = validate_field(field, target)
            status = 'Matches reference' if normalized == target_value else 'Differs from reference'
        except (ValueError, TypeError):
            status = 'Not evaluated'
        rows.append({
            'field': field, 'current': value, 'reference': target,
            'status': status, 'can_apply': False,
            'explanation': 'Reference comparison only; no performance-based change is implied.'})

    return {
        'rows': rows, 'recommendations': recommendations,
        'evidence_reasons': reasons,
        'confidence': 'insufficient observations' if reasons else 'limited local observations',
        'evidence': evidence, 'source': SOURCE}
