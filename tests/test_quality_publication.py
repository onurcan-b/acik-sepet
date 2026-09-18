"""Regression cases from the 14 September audit; no network access."""
import copy
import csv
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from acik_sepet import collect, index
from acik_sepet.history import verify_files
from acik_sepet.product_types import load_product_types, load_product_types_for_date
from acik_sepet.validate import validate_rows, validate_source_evidence


def item(key='a', price=100):
    return {'id': key, 'title': 'Normal Süt 1 Lt', 'refinedVolumeOrWeight': '1 LT',
            'categories': ['Süt'], 'productDepotInfoList': [
                {'depotId': 'd1', 'price': price, 'unitPriceValue': price,
                 'marketAdi': 'A', 'indexTime': '15.09.2026 08:00'}]}


def spec():
    return {'id': 'milk', 'label': 'Süt', 'group': 'g', 'query': 'süt', 'unit': 'volume',
            'target_skus': 5, 'min_skus': 1, 'include_tokens': ['süt'],
            'exclude_tokens': [], 'api_category_level': 'sub_category', 'api_categories': ['Süt']}


@pytest.fixture
def collector(tmp_path, monkeypatch):
    data = tmp_path / 'data/v0.4'
    snapshots = data / 'snapshots'
    snapshots.mkdir(parents=True)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/series.json').write_text(json.dumps({'baseline_date': '2026-09-05', 'locked_through': '2026-09-14'}))
    panel = tmp_path / 'state/panel.json'
    panel.parent.mkdir()
    state, rows = collect._initialize_type([item()], spec(), set(), '2026-09-14')
    panel.write_text(json.dumps({'types': {'milk': state}}))
    for name, value in [('ROOT', tmp_path), ('DATA_DIR', data), ('SNAPSHOT_DIR', snapshots), ('PANEL_PATH', panel)]:
        monkeypatch.setattr(collect, name, value)
    monkeypatch.setattr(collect, 'load_product_types_for_date', lambda _: [spec()])
    monkeypatch.setattr(collect.time, 'sleep', lambda _: None)
    import acik_sepet.validate as validation
    monkeypatch.setattr(validation, 'validate_rows', lambda rows, day, specs: validate_rows(rows, day, min_skus=1, specs=specs))
    class Clock(datetime):
        @classmethod
        def now(cls, tz): return datetime(2026, 9, 15, 12, tzinfo=tz)
    monkeypatch.setattr(collect, 'datetime', Clock)
    return snapshots, panel, rows


def test_failed_api_cannot_overwrite_existing_snapshot_or_panel(collector, monkeypatch):
    snapshots, panel, _ = collector
    # Two files avoid the initial-baseline refresh guard.
    (snapshots / '2026-09-14.csv').write_text('date,slot_id,product_key,linked_unit_price\n')
    target = snapshots / '2026-09-15.csv'
    target.write_text('date,slot_id,product_key,linked_unit_price\n')
    before = target.read_bytes(), panel.read_bytes()
    calls = []
    def failed(*a, **kw):
        calls.append(1)
        raise collect.MarketFiyatiError('pagination disconnected')
    monkeypatch.setattr(collect, 'search_products', failed)
    with pytest.raises(SystemExit, match='Toplama eksik'):
        collect.collect(refresh=True)
    assert len(calls) == 4
    assert (target.read_bytes(), panel.read_bytes()) == before
    status = json.loads((snapshots.parent / 'collection-status.json').read_text())
    assert status['status'] == 'rejected' and len(status['errors']) == 1


def test_refresh_never_rescans_the_locked_last_day(collector, monkeypatch):
    snapshots, panel, _ = collector
    target = snapshots / '2026-09-14.csv'
    target.write_text('protected observation')
    class LockedClock(datetime):
        @classmethod
        def now(cls, tz): return datetime(2026, 9, 14, 16, tzinfo=tz)
    monkeypatch.setattr(collect, 'datetime', LockedClock)
    def unexpected(*args, **kwargs): raise AssertionError('historical day was rescanned')
    monkeypatch.setattr(collect, 'search_products', unexpected)
    before = target.read_bytes(), panel.read_bytes()
    assert collect.collect(refresh=True) == target
    assert (target.read_bytes(), panel.read_bytes()) == before


def test_retry_recovers_and_publishes_verifiable_source_evidence(collector, monkeypatch):
    snapshots, panel, _ = collector
    calls = []
    def retry(*a, **kw):
        calls.append(1)
        if len(calls) == 1: raise collect.MarketFiyatiError('temporary disconnection')
        return [item(price=110)]
    monkeypatch.setattr(collect, 'search_products', retry)
    result = collect.collect()
    rows = list(csv.DictReader(result.open()))
    assert float(rows[0]['linked_unit_price']) == pytest.approx(110)
    validate_source_evidence(rows[0])
    assert json.loads(rows[0]['source_link'])['previous_prices'] == {'depot:d1': 100}
    status = json.loads((snapshots.parent / 'collection-status.json').read_text())
    assert status['status'] == 'published' and status['recovered_types'] == ['milk']


def test_invalid_freshness_cannot_write_snapshot_or_state(collector, monkeypatch):
    snapshots, panel, _ = collector
    old_state = panel.read_bytes()
    stale = item()
    stale['productDepotInfoList'][0]['indexTime'] = '01.09.2026 08:00'
    monkeypatch.setattr(collect, 'search_products', lambda *a, **kw: [stale])
    with pytest.raises(SystemExit, match='güncelliği'):
        collect.collect()
    assert not (snapshots / '2026-09-15.csv').exists()
    assert panel.read_bytes() == old_state


def test_recovery_exhaustion_preserves_state_even_with_successful_types(collector, monkeypatch):
    snapshots, panel, _ = collector
    old_state = panel.read_bytes()
    specs = [spec(), {**spec(), 'id': 'other', 'query': 'other'}]
    monkeypatch.setattr(collect, 'load_product_types_for_date', lambda _: specs)
    calls = []

    def fetch(query, **kwargs):
        calls.append(query)
        if query == 'other':
            raise collect.MarketFiyatiError('remote disconnected')
        return [item(price=110)]

    monkeypatch.setattr(collect, 'search_products', fetch)
    with pytest.raises(SystemExit, match='Toplama eksik'):
        collect.collect()
    assert calls.count('süt') == 1 and calls.count('other') == 4
    assert panel.read_bytes() == old_state
    assert not (snapshots / '2026-09-15.csv').exists()
    status = json.loads((snapshots.parent / 'collection-status.json').read_text())
    assert status['status'] == 'rejected' and status['observed_skus'] == 1
    assert [row['type_id'] for row in status['errors']] == ['other']


def test_crossing_midnight_cannot_publish_misdated_observations(collector, monkeypatch):
    snapshots, panel, _ = collector
    old_state = panel.read_bytes()

    class Clock(datetime):
        day = 15

        @classmethod
        def now(cls, tz):
            return datetime(2026, 9, cls.day, 0, tzinfo=tz)

    def fetch(*args, **kwargs):
        Clock.day = 16
        return [item(price=110)]

    monkeypatch.setattr(collect, 'datetime', Clock)
    monkeypatch.setattr(collect, 'search_products', fetch)
    with pytest.raises(SystemExit, match='crossed midnight'):
        collect.collect()
    assert panel.read_bytes() == old_state
    assert not list(snapshots.glob('*.csv'))
    status = json.loads((snapshots.parent / 'collection-status.json').read_text())
    assert status['status'] == 'rejected'


def test_same_day_refresh_cannot_silently_erase_category():
    specs = [spec()]
    old = [{'type_id': 'milk'} for _ in range(5)]
    assert collect._refresh_regression(old, [], specs)
    assert collect._refresh_regression(old, old[:3], specs)
    assert collect._refresh_regression(old, old[:4], specs) is None


def test_depot_evidence_detects_tampering():
    state, rows = collect._initialize_type([item()], spec(), set(), '2026-09-15')
    row = rows[0]
    validate_source_evidence(row)
    row['linked_unit_price'] *= 1.2
    with pytest.raises(SystemExit, match='bağlı fiyat uyuşmuyor'):
        validate_source_evidence(row)


@pytest.mark.parametrize('type_id,title', [
    ('bread_white', 'Normal Kepekli Ekmek 200 Gr'),
    ('bread_white', 'İHE Fındıklı Ve Üzümlü Ekmek 50 Gr'),
    ('bread_white', 'Uno Çok Tahıllı Ekmek 460 Gr'),
    ('bread_white', 'Schar Pan Rustico Glutensiz Ekmek 250 Gr'),
    ('milk', 'Sek Laktozsuz Süt 1 Lt'),
    ('milk', 'Dost İtalyan Karamelli Pastörize Süt 1 Lt'),
    ('whole_chicken', 'Tazem Piliç Izgara Mangal 1 Kg'),
    ('tomato', 'Şeker Domates 250 Gr'),
    ('beef_cubes', 'Dana Bonfile 500 Gr'),
])
def test_audited_misclassifications_rejected_prospectively(type_id, title):
    current = {s['id']: s for s in load_product_types()}
    previous = {s['id']: s for s in load_product_types_for_date('2026-09-14')}
    assert not collect._title_matches(title, current[type_id])
    assert collect._title_matches(title, previous[type_id])


def test_definition_replacement_is_bridged_without_price_jump():
    old_spec = spec()
    state, _ = collect._initialize_type([item('old', 100)], old_spec, set(), '2026-09-14')
    state['skus'][0]['title'] = 'Laktozsuz Süt 1 Lt'
    corrected = {**old_spec, 'exclude_tokens': ['laktozsuz']}
    state['candidates'] = {'id:new': {'last_seen': '2026-09-14', 'seen_streak': 2}}
    observations = collect._observe_type([item('new', 500)], corrected, state, {'id:old'}, '2026-09-15', {})
    assert len(observations) == 1
    assert observations[0]['slot_id'] == 'id:old'
    assert observations[0]['product_key'] == 'id:new'
    assert observations[0]['linked_unit_price'] == pytest.approx(100)
    validate_source_evidence(observations[0])


@pytest.mark.parametrize('extra_days', [0, 1, 7])
def test_frozen_series_extends_from_original_level_and_cannot_be_rewritten(tmp_path, monkeypatch, extra_days):
    repo = Path(__file__).resolve().parents[1]
    shutil.copytree(repo / 'config', tmp_path / 'config')
    data = tmp_path / 'data/v0.4'
    # Live snapshots keep growing. Only the immutable history belongs in this
    # fixture; every day after the lock must be controlled by this test.
    lock = json.loads((tmp_path / 'config/history-lock.json').read_text())
    for name in lock['files']:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / name, target)
    monkeypatch.setattr(index, 'ROOT', tmp_path)
    monkeypatch.setattr(index, 'SNAPSHOT_DIR', data / 'snapshots')
    for attr, name in [('INDEX_PATH', 'index.csv'), ('TYPE_PATH', 'type_indices.csv'), ('CATEGORY_PATH', 'category_indices.csv')]:
        monkeypatch.setattr(index, attr, data / name)
    rows = list(csv.DictReader((data / 'snapshots/2026-09-14.csv').open()))
    for row in rows:
        for field in ['price', 'unit_price', 'linked_unit_price']:
            row[field] = str(float(row[field]) * 1.01)
    first_new_day = date(2026, 9, 15)
    for offset in range(extra_days + 1):
        day = (first_new_day + timedelta(days=offset)).isoformat()
        for row in rows:
            row['date'] = day
        target = data / 'snapshots' / f'{day}.csv'
        with target.open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator='\n')
            writer.writeheader(); writer.writerows(rows)
    result = index.rebuild()
    assert result[0]['index'] == 100 and result[0]['date'] == '2026-09-05'
    assert all(row['baseline_date'] == '2026-09-05' for row in result)
    extension = [row for row in result if row['date'] >= first_new_day.isoformat()]
    assert [row['date'] for row in extension] == [
        (first_new_day + timedelta(days=offset)).isoformat() for offset in range(extra_days + 1)]
    # A 1% move on the first new day, then unchanged prices on later days.
    assert [row['index'] for row in extension] == pytest.approx(
        [99.7265 * 1.01] * (extra_days + 1), abs=0.0002)
    for name in ['index.csv', 'type_indices.csv', 'category_indices.csv']:
        frozen = (data / 'frozen-2026-09-14' / name).read_text()
        assert (data / name).read_text().startswith(frozen)
    historical = data / 'snapshots/2026-09-14.csv'
    historical.write_text(historical.read_text().replace('15.0', '16.0', 1))
    with pytest.raises(ValueError, match='Protected historical file'):
        verify_files(tmp_path)


def test_current_chart_bytes_are_preserved_but_new_data_extends_it(tmp_path, monkeypatch):
    import hashlib
    from acik_sepet import report
    repo = Path(__file__).resolve().parents[1]
    chart = tmp_path / 'index.svg'
    original = (repo / 'charts/index.svg').read_bytes()
    chart.write_bytes(original)
    data = tmp_path / 'index.csv'
    data.write_bytes((repo / 'data/v0.4/index.csv').read_bytes())
    (tmp_path / 'index-input.sha256').write_text(hashlib.sha256(data.read_bytes()).hexdigest())
    monkeypatch.setattr(report, 'CHART_DIR', tmp_path)
    monkeypatch.setattr(report, 'INDEX_PATH', data)
    monkeypatch.setattr(report, '_render_coverage_charts', lambda *args: None)
    rows = list(csv.DictReader(data.open()))
    report.render_charts(rows, [], [])
    assert chart.read_bytes() == original
    new_row = dict(rows[-1])
    new_row['date'] = (date.fromisoformat(new_row['date']) + timedelta(days=1)).isoformat()
    # The latest real index can be blank when category coverage is insufficient.
    new_row['index'] = '101.0'
    with data.open('a', newline='') as handle:
        csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator='\n').writerow(new_row)
    rows = list(csv.DictReader(data.open()))
    report.render_charts(rows, [], [])
    assert chart.read_bytes() != original


def test_report_reveals_collection_failure_instead_of_fresh_flat_prices(tmp_path, monkeypatch):
    from acik_sepet import report
    monkeypatch.setattr(report, 'DATA_DIR', tmp_path)
    (tmp_path / 'collection-status.json').write_text(json.dumps({
        'status': 'rejected', 'date': '2026-09-15', 'reason': 'network error',
        'checked_at': '2026-09-15T12:00:00+03:00',
        'errors': [{'type_id': 'shampoo', 'error': 'network'}]}))
    text = report._status([{'date': '2026-09-14', 'coverage': '0.77'}],
        [{'date': '2026-09-14', 'label': 'Kişisel bakım', 'index': ''}],
        [{'date': '2026-09-14', 'slot_id': 'a', 'source_updated_at': '13.09.2026 08:00'}])
    assert 'Tarama başarısız; önceki yayın korundu' in text
    assert '0/1' in text and 'Kişisel bakım' in text


def test_one_sku_loss_in_small_panel_is_not_a_publication_failure():
    garlic = {**spec(), 'id': 'garlic', 'min_skus': 2}
    before = [{'type_id': 'garlic'}] * 4
    assert collect._refresh_regression(before, before[:3], [garlic]) is None
    assert collect._refresh_regression(before, before[:1], [garlic]) is not None


def test_report_distinguishes_failed_requests_from_unattempted_types(tmp_path, monkeypatch):
    from acik_sepet import report
    monkeypatch.setattr(report, 'DATA_DIR', tmp_path)
    (tmp_path / 'collection-status.json').write_text(json.dumps({
        'status': 'rejected', 'errors': [
            {'type_id': 'milk', 'error': 'remote disconnected'},
            {'type_id': 'other', 'error': 'budget exhausted', 'not_scanned': True}]}))
    text = report._status([{'date': '2026-09-15', 'coverage': '0.74'}], [], [])
    assert '1 ürün tipinde API hatası' in text
    assert '1 ürün tipi taranamadı' in text
    assert 'Tarama başarısız; önceki yayın korundu' in text


@pytest.mark.parametrize('remaining,retain', [(3, False), (1, True)])
def test_same_day_drop_preserves_only_affected_type_and_its_state(collector, monkeypatch, remaining, retain):
    snapshots, panel, _ = collector
    specs = [{**spec(), 'min_skus': 2}, {**spec(), 'id': 'other', 'query': 'other', 'label': 'Other'}]
    states = {}
    previous_rows = []
    for current_spec, items in [(specs[0], [item(str(i)) for i in range(4)]), (specs[1], [item('other', 200)])]:
        state, rows = collect._initialize_type(items, current_spec, set(), '2026-09-15')
        states[current_spec['id']] = state
        for row in rows:
            row.update(date='2026-09-15', type_id=current_spec['id'], type_label=current_spec['label'],
                       group='g', collected_at='2026-09-15T09:00:00+03:00', match_score=row.pop('score'))
        previous_rows.extend(rows)
    panel.write_text(json.dumps({'types': states}))
    original = copy.deepcopy(states)
    (snapshots / '2026-09-14.csv').write_text('date,slot_id,product_key,linked_unit_price\n')
    with (snapshots / '2026-09-15.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=previous_rows[0].keys())
        writer.writeheader(); writer.writerows(previous_rows)
    monkeypatch.setattr(collect, 'load_product_types_for_date', lambda _: specs)
    monkeypatch.setattr(collect, 'search_products', lambda query, **kwargs:
                        [item('other', 220)] if query == 'other' else [item(str(i), 110) for i in range(remaining)])
    published = collect.collect(refresh=True)
    output = list(csv.DictReader(published.open()))
    status = json.loads((snapshots.parent / 'collection-status.json').read_text())
    saved_states = json.loads(panel.read_text())['types']
    milk = [r for r in output if r['type_id'] == 'milk']
    other = [r for r in output if r['type_id'] == 'other']
    assert float(other[0]['linked_unit_price']) == 220
    if retain:
        assert saved_states['milk'] == original['milk']
        assert len(milk) == 4
        assert all(r['collected_at'] == '2026-09-15T09:00:00+03:00' and float(r['linked_unit_price']) == 100 for r in milk)
        assert status['status'] == 'published_with_retained_types'
        assert [r['type_id'] for r in status['retained_same_day_types']] == ['milk']
    else:
        assert len(milk) == 3
        assert all(float(r['linked_unit_price']) == 110 for r in milk)
        assert status['status'] == 'published'
    for row in output: validate_source_evidence(row)


def test_retention_never_carries_yesterdays_observations():
    old = [{'type_id': 'milk', 'date': '2026-09-14', 'collected_at': '2026-09-14T09:00:00+03:00'}]
    current, state = {'milk': []}, {'milk': {'value': 'new'}}
    retained = collect._retain_same_day_types(old, current, state, {'milk': {'value': 'old'}}, [spec()], '2026-09-15')
    assert retained == [] and current['milk'] == [] and state['milk']['value'] == 'new'


def test_status_discloses_retained_measurement_time(tmp_path, monkeypatch):
    from acik_sepet import report
    monkeypatch.setattr(report, 'DATA_DIR', tmp_path)
    (tmp_path / 'collection-status.json').write_text(json.dumps({
        'status': 'published_with_retained_types', 'errors': [],
        'retained_same_day_types': [{'label': 'Maydanoz', 'collected_at': ['2026-09-15T03:00:00+03:00']}]}))
    text = report._status([{'date': '2026-09-15', 'coverage': '0.74'}], [], [])
    assert 'Kısmi güncelleme' in text and 'Maydanoz' in text and '03:00:00' in text
