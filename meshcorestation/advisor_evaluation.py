"""Descriptive before/after measurements for verified repeater advisor writes.

These are companion-observed traffic ratios, never proof of improved delivery.
"""
import time
from contextlib import closing
from meshcorestation.storage import passive_stats

WINDOW = 86400
SETTLING = 3600
MAX_EVALUATIONS = 10


def sample(db, key, start, stop):
    row = db.execute("""
        SELECT COUNT(*) copies, COUNT(digest) identified,
               COUNT(DISTINCT digest) unique_payloads,
               COALESCE(SUM(scoped=0),0) unscoped,
               COALESCE(SUM(kind=4),0) advertisements,
               COUNT(DISTINCT route) routes
        FROM observations
        WHERE target=? AND ambiguous=0 AND at>=? AND at<?
    """, (key, start, stop)).fetchone()
    data = dict(row)
    data['repeated'] = data['identified'] - data['unique_payloads']
    data['repeat_pct'] = round(100 * data['repeated'] / data['identified'], 1) if data['identified'] else None
    data['unscoped_pct'] = round(100 * data['unscoped'] / data['copies'], 1) if data['copies'] else None
    data['advert_pct'] = round(100 * data['advertisements'] / data['copies'], 1) if data['copies'] else None
    return data


def evaluate_recent(key, changes, now=None):
    """Equal 24-hour samples, 1-hour settling, conservative comparability gate."""
    if not key:
        return {}
    now = time.time() if now is None else now
    verified = [row for row in changes if row.get('status') == 'verified'
                and row.get('actual') == row.get('requested')]
    if not verified:
        return {}
    with closing(passive_stats.connect()) as db:
        db.execute('BEGIN')
        selected = db.execute('SELECT * FROM selection WHERE id=1').fetchone()
        health = db.execute('SELECT * FROM health WHERE id=1').fetchone()
        selection = dict(selected) if selected else {}
        health = dict(health) if health else {}
        results = {}
        for change in verified[:MAX_EVALUATIONS]:
            ident, at = str(change['id']), change['at']
            entry = {'status': 'unavailable', 'message': 'Comparison unavailable.',
                     'window_hours': 24, 'settling_hours': 1, 'notes': []}
            results[ident] = entry
            if selection.get('public_key') != key:
                entry['message'] = 'Select this repeater in Repeater Statistics.'
                continue
            if not isinstance(at, (float, int)) or not 0 < at <= now:
                entry['message'] = 'Change time is invalid.'
                continue
            before_start, after_start = at - WINDOW, at + SETTLING
            after_end = after_start + WINDOW
            if before_start < now - passive_stats.RETENTION:
                entry['message'] = 'Baseline passed the 30-day statistics retention period.'
                continue
            if selection.get('since', now) > before_start:
                entry['message'] = 'Selected-repeater collection did not cover the full baseline.'
                continue
            if health.get('trimmed_at') and health['trimmed_at'] >= before_start:
                entry['message'] = 'History was truncated; baseline completeness is unverified.'
                continue
            if now < after_end:
                entry.update(status='collecting', next_at=after_end,
                             message='Collecting 24 hours after 1 hour of settling.')
                continue
            before = sample(db, key, before_start, at)
            after = sample(db, key, after_start, after_end)
            entry.update(before=before, after=after)
            if (min(before['copies'], after['copies']) < 100 or
                    min(before['identified'], after['identified']) < 70):
                entry.update(status='insufficient', message='Too few observations in one or both 24-hour windows.')
                continue
            if (min(before['identified']/before['copies'], after['identified']/after['copies']) < .70 or
                    min(before['identified'], after['identified']) / max(before['identified'], after['identified']) < .5):
                entry.update(status='incomparable', message='Identifiable traffic volume or completeness differs too much.')
                continue
            others = sum(1 for item in changes if item['id'] != change['id']
                         and isinstance(item.get('at'), (float, int))
                         and before_start <= item['at'] <= after_end)
            delta = {name: round(after[name] - before[name], 1)
                     for name in ('repeat_pct', 'unscoped_pct', 'advert_pct')}
            difference = delta['repeat_pct']
            entry.update(status='descriptive', confounded_changes=others,
                         delta_percentage_points=delta,
                         message=('Lower' if difference <= -10 else
                                  'Higher' if difference >= 10 else 'Similar') +
                                 ' observed repeated-payload share.',
                         notes=[
                             'Companion-visible paths only; delivery success, total repeater load and causality are unknown.',
                             'Traffic mix and manual/external settings can differ across windows.'])
            if others:
                entry['notes'].append(f'{others} other advisor changes in the interval; no single-setting attribution.')
            if health.get('dropped'):
                entry['notes'].append('The collector reported packet drops, but their timing is unknown.')
        return results
