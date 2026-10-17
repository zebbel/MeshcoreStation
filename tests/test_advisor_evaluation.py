"""Regression tests for descriptive before/after advisor observations."""
import time
import pytest
from meshcorestation.storage import passive_stats
from meshcorestation import advisor_evaluation as evaluation

KEY = 'ab' * 32


@pytest.fixture
def traffic(tmp_path, monkeypatch):
    monkeypatch.setattr(passive_stats, 'STATS_PATH', tmp_path / 'statistics.db')
    passive_stats.initialize()

    def seed(at, *, before=150, after=150, sparse_after=False, since=None, trimmed=None, dropped=0):
        with passive_stats.connect() as db:
            db.execute('INSERT OR REPLACE INTO selection VALUES(1,?,?)',
                       (KEY, at - 10 * 86400 if since is None else since))
            db.execute('UPDATE health SET trimmed_at=?,dropped=? WHERE id=1',
                       (trimmed, dropped))
            rows = []
            for label, start, count, repeats in [('before', at - 86400, before, 100),
                                                  ('after', at + 3600, after, 10)]:
                for index in range(count):
                    digest = f'{label}-{index if index >= repeats else 0}'
                    if label == 'after' and sparse_after and index % 3 == 0:
                        digest = None
                    rows.append((KEY, start + index + 100, digest,
                                 4 if index % 3 else 5, index % 2,
                                 0, 1, 0, 0, '[{},{}]' if index % 2 else '[{}]',
                                 '[]', '[]'))
            db.executemany('''INSERT INTO observations
                (target,at,digest,kind,scoped,ambiguous,first_hop,middle_hop,
                 last_hop,route,previous,following)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', rows)
        return at

    return seed


def change(at, ident=1, **overrides):
    row = {'id': ident, 'at': at, 'public_key': KEY, 'field': 'loop.detect',
           'before_value': 'off', 'requested': 'minimal',
           'actual': 'minimal', 'status': 'verified'}
    row.update(overrides)
    return row


def test_evaluation_waits_for_full_after_window(traffic):
    at = traffic(time.time() - 26 * 3600)
    row = evaluation.evaluate_recent(KEY, [change(at)], now=at + 2 * 3600)['1']
    assert row['status'] == 'collecting'
    assert row['next_at'] == at + 25 * 3600


def test_equal_window_comparison_reports_ratios_not_delivery(traffic):
    at = traffic(time.time() - 26 * 3600)
    row = evaluation.evaluate_recent(KEY, [change(at)], now=at + 26 * 3600)['1']
    assert row['status'] == 'descriptive'
    assert row['before']['copies'] == row['after']['copies'] == 150
    assert row['delta_percentage_points']['repeat_pct'] < 0
    assert row['window_hours'] == 24 and row['settling_hours'] == 1
    assert any('causality' in note for note in row['notes'])


def test_wrong_selection_and_incomplete_baseline_rejected(traffic):
    at = traffic(time.time() - 26 * 3600, since=time.time() - 1000)
    row = evaluation.evaluate_recent(KEY, [change(at)], now=at + 26 * 3600)['1']
    assert row['status'] == 'unavailable'
    assert evaluation.evaluate_recent('cd' * 32, [change(at)], now=at + 26 * 3600)['1']['status'] == 'unavailable'


def test_traffic_completeness_gate(traffic):
    at = traffic(time.time() - 26 * 3600, before=200, after=150, sparse_after=True)
    row = evaluation.evaluate_recent(KEY, [change(at)], now=at + 26 * 3600)['1']
    assert row['status'] == 'incomparable'


def test_insufficient_samples(traffic):
    at = traffic(time.time() - 26 * 3600, before=30, after=30)
    row = evaluation.evaluate_recent(KEY, [change(at)], now=at + 26 * 3600)['1']
    assert row['status'] == 'insufficient'


def test_other_change_and_dropped_observations_get_warnings(traffic):
    at = traffic(time.time() - 26 * 3600, dropped=5)
    rows = [change(at), change(at + 900, ident=2, field='flood.max',
                               before_value='32', requested='16', actual='16')]
    result = evaluation.evaluate_recent(KEY, rows, now=at + 26 * 3600)['1']
    assert result['status'] == 'descriptive'
    assert result['confounded_changes'] == 1
    assert any('dropped' in note for note in result['notes'])
    assert any('other advisor changes' in note for note in result['notes'])


def test_truncation_prevents_comparison(traffic):
    at = time.time() - 26 * 3600
    traffic(at, trimmed=at)
    row = evaluation.evaluate_recent(KEY, [change(at)], now=at + 26 * 3600)['1']
    assert row['status'] == 'unavailable'


def test_only_verified_writes_are_evaluated(traffic):
    at = traffic(time.time() - 26 * 3600)
    rows = [change(at, status='unconfirmed'), change(at, ident=2, actual='off')]
    assert evaluation.evaluate_recent(KEY, rows, now=at + 26 * 3600) == {}
