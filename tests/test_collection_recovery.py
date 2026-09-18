"""Reproduce sustained upstream interruptions with a fake clock, never sleeps."""
from collections import Counter

import pytest

from acik_sepet import collect
from acik_sepet.api import MarketFiyatiError


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 0.0
        sleeps = []

        def sleep(self, delay):
            self.sleeps.append(delay)
            self.now += delay

    clock = Clock()
    monkeypatch.setattr(collect.time, 'monotonic', lambda: clock.now)
    monkeypatch.setattr(collect.time, 'sleep', clock.sleep)
    return clock


def test_outage_pauses_new_requests_and_only_retries_unfinished_types(clock):
    specs = [{'id': str(i)} for i in range(7)]
    calls = []

    def scan(spec):
        calls.append((spec['id'], clock.now))
        if spec['id'] != '0' and clock.now < 60:
            raise MarketFiyatiError('remote disconnected')

    errors, recovered, recovery = collect._scan_with_recovery(specs, scan)
    assert errors == []
    assert [key for key, _ in calls] == ['0', '1', '2', '3', '1', '2', '3', '4', '5', '6']
    assert calls[3][1] == 0 and calls[4][1] == 60
    assert recovered == ['1', '2', '3']
    assert recovery[0]['remaining_types'] == ['1', '2', '3', '4', '5', '6']
    assert Counter(key for key, _ in calls)['0'] == 1


def test_persistent_outage_is_bounded_and_reports_unattempted_types(clock):
    calls = []

    def scan(spec):
        calls.append(spec['id'])
        raise MarketFiyatiError('remote disconnected')

    errors, recovered, recovery = collect._scan_with_recovery([{'id': str(i)} for i in range(8)], scan)
    assert len(calls) == 12  # 3 failed types in each of 4 bounded passes.
    assert len(errors) == 8 and not recovered
    assert clock.sleeps == [60, 180, 300]
    assert [row['type_id'] for row in errors if row.get('not_scanned')] == ['3', '4', '5', '6', '7']


def test_retry_after_pauses_the_entire_source_not_only_failed_query(clock):
    calls = []

    def scan(spec):
        calls.append((spec['id'], clock.now))
        if len(calls) == 1:
            raise MarketFiyatiError('rate limited', retry_after=120)

    errors, recovered, _ = collect._scan_with_recovery([{'id': 'a'}, {'id': 'b'}], scan)
    assert errors == [] and recovered == ['a']
    assert calls == [('a', 0), ('a', 120), ('b', 120)]
    assert clock.sleeps == [120]


def test_does_not_retry_earlier_than_server_allows_when_budget_is_short(clock):
    calls = []

    def scan(spec):
        calls.append(spec['id'])
        raise MarketFiyatiError('rate limited', retry_after=3600)

    errors, _, _ = collect._scan_with_recovery([{'id': 'a'}, {'id': 'b'}], scan)
    assert calls == ['a'] and not clock.sleeps
    assert len(errors) == 2 and errors[1]['not_scanned']


def test_permanent_error_stops_without_retrying_or_scanning_other_types(clock):
    calls = []

    def scan(spec):
        calls.append(spec['id'])
        raise MarketFiyatiError('invalid API schema', retryable=False)

    errors, _, recovery = collect._scan_with_recovery([{'id': 'a'}, {'id': 'b'}], scan)
    assert calls == ['a'] and not clock.sleeps and not recovery
    assert errors[0]['retryable'] is False and errors[1]['not_scanned']


def test_elapsed_budget_stops_before_next_type(clock, monkeypatch):
    monkeypatch.setattr(collect, 'MAX_COLLECTION_SECONDS', 10)
    calls = []

    def scan(spec):
        calls.append(spec['id'])
        clock.now += 11

    errors, _, _ = collect._scan_with_recovery([{'id': 'a'}, {'id': 'b'}], scan)
    assert calls == ['a'] and not clock.sleeps
    assert errors == [{'type_id': 'b', 'error': 'Collection time budget exhausted', 'not_scanned': True}]
