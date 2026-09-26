"""Dashboard semantics: gaps, contributor denominators, and stale observations."""
import json
import math
from pathlib import Path

import pytest

from acik_sepet import report


def test_calendar_changes_do_not_bridge_missing_dates_or_zero_denominators():
    rows = [{'date': '2026-09-05', 'index': '100'}, {'date': '2026-09-07', 'index': '98'}]
    assert report._change(rows, 1) is None
    assert report._change(rows, 2) == pytest.approx(-2)
    rows[1]['index'] = '100'
    assert report._change(rows, 2) == 0
    rows[0]['index'] = '0'
    assert report._change(rows, 2) is None


def test_heatmap_has_missing_cells_and_never_bridges_gap():
    rows = [{'date': day, 'group_id': 'fruit', 'index': value} for day, value in [
        ('2026-09-05', '100'), ('2026-09-06', '100'), ('2026-09-08', '110'), ('2026-09-09', '')]]
    groups, values = report._heatmap_values(rows, report._calendar('2026-09-09', 5))
    assert groups == ['fruit']
    assert values[0][1] == 0
    assert all(math.isnan(values[0][i]) for i in [0, 2, 3, 4])


def test_breadth_keeps_missing_types_and_stale_flat_separate(monkeypatch):
    monkeypatch.setattr(report, 'load_product_types', lambda: [{'id': key} for key in ['up', 'down', 'flat', 'stale', 'missing']])
    rows, days = [], []
    for day, new in [('2026-09-05', False), ('2026-09-06', True)]:
        types = []
        for key in ['up', 'down', 'flat', 'stale']:
            rows.append({'date': day, 'type_id': key, 'label': key, 'index': 101 if new and key == 'up' else 99 if new and key == 'down' else 100})
            types.append({'type_id': key, 'fresh_within_1_day_share': .2 if key == 'stale' else 1})
        days.append({'date': day, 'types': types})
    _, changes, counts = report._daily_moves(rows, {'days': days})
    assert counts == {'up': 1, 'down': 1, 'flat': 1, 'limited': 1, 'unavailable': 1}
    assert not next(row for row in changes if row['type_id'] == 'stale')['fresh']
    # Missing preceding calendar date invalidates every comparison.
    rows = [row for row in rows if row['date'] != '2026-09-05']
    assert report._daily_moves(rows, {'days': days})[2]['unavailable'] == 5


def test_stats_use_actual_headline_contributors_and_exact_periods():
    rows = [{'date': '2026-09-05', 'index': '100', 'baseline_date': '2026-09-05', 'coverage': '1'},
            {'date': '2026-09-12', 'index': '101', 'baseline_date': '2026-09-05', 'coverage': '.66', 'types': '102', 'skus': '1515'}]
    quality = {'days': [{'date': '2026-09-12', 'headline_types': 80, 'headline_skus': 1354, 'collected_skus': 1605}]}
    text = report._stats(rows, quality)
    assert '80 tip / 1354 SKU' in text and '1605 SKU' in text
    assert '| — | +1.00% | — | +1.00%' in text
    assert '1515' not in text and '102' not in text


def test_retailer_deltas_need_exact_seven_day_evidence():
    quality = {'days': [
        {'date': '2026-09-05', 'sources': {'retailers': [{'market': 'one', 'skus': 7, 'depots': None}]}},
        {'date': '2026-09-12', 'sources': {'retailers': [{'market': 'one', 'skus': 5, 'depots': 2}]}}]}
    row = report._retailer_rows(quality)[1][0]
    assert row['delta'] == -2 and row['depot_delta'] is None
    quality['days'][0]['date'] = '2026-09-04'
    assert report._retailer_rows(quality)[1][0]['delta'] is None


def test_six_svg_assets_render_zero_negative_missing_and_invalidate_on_quality(tmp_path, monkeypatch):
    monkeypatch.setattr(report, 'CHART_DIR', tmp_path)
    monkeypatch.setattr(report, 'load_product_types', lambda: [])
    index = [{'date': '2026-09-05', 'index': '100', 'coverage': '1', 'baseline_date': '2026-09-05'},
             {'date': '2026-09-06', 'index': '', 'coverage': '.4', 'baseline_date': '2026-09-05'},
             {'date': '2026-09-07', 'index': '99', 'coverage': '.8', 'baseline_date': '2026-09-05'}]
    cats = [{'date': row['date'], 'group_id': 'fruit', 'label': 'Meyve', 'index': row['index']} for row in index]
    quality = {'days': [{'date': r['date'], 'partial_coverage': False} for r in index]}
    report.render_charts(index, cats, [], quality=quality)
    assert {path.name for path in tmp_path.glob('*.svg')} == set(report.CHART_FILENAMES)
    original = (tmp_path / 'index.svg').read_bytes()
    stamp = (tmp_path / 'index-input.sha256').read_bytes()
    report.render_charts(index, cats, [], quality=quality)
    assert (tmp_path / 'index.svg').read_bytes() == original
    quality['days'][-1]['partial_coverage'] = True
    report.render_charts(index, cats, [], quality=quality)
    assert (tmp_path / 'index.svg').read_bytes() != original
    assert (tmp_path / 'index-input.sha256').read_bytes() != stamp
    assert 'Kısmi kapsam' in (tmp_path / 'index.svg').read_text(encoding='utf-8')


def test_status_only_preserves_every_chart_and_stats(tmp_path, monkeypatch):
    from acik_sepet import diagnostics
    readme = tmp_path / 'README.md'
    readme.write_text('<!-- STATUS_START -->\nold\n<!-- STATUS_END -->\n<!-- STATS_START -->\nkeep\n<!-- STATS_END -->', encoding='utf-8')
    monkeypatch.setattr(report, 'README_PATH', readme)
    monkeypatch.setattr(report, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(report, '_read', lambda path: [{'date': '2026-09-26', 'index': '100', 'coverage': '.66'}])
    monkeypatch.setattr(report, '_latest_snapshot', lambda: [])
    monkeypatch.setattr(diagnostics, 'build', lambda root: {'days': []})
    monkeypatch.setattr(report, 'render_charts', lambda *a, **k: pytest.fail('status-only regenerated charts'))
    (tmp_path / 'collection-status.json').write_text(json.dumps({'status': 'rejected', 'reason': 'offline'}))
    report.main(status_only=True)
    text = readme.read_text(encoding='utf-8')
    assert 'Tarama başarısız; önceki yayın korundu' in text
    assert '<!-- STATS_START -->\nkeep\n<!-- STATS_END -->' in text
