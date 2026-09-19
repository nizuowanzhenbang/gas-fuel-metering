"""对账必须说明计量区间，不能把缺数、复位或错位回路当成正常结果。"""
import pytest
from backend.tests.test_reconciliation_router import _create_source, _create_station, _post_reading
from backend.tests.test_upload_router import _xlsx, _upload


def setup(client, headers, points):
    sid = _create_source(client, headers)
    station = _create_station(client, headers, source_id=sid)
    for ts, value in points:
        _post_reading(client, headers, station_id=station, ts=ts, accumulated_volume_nm3=value)
    return sid, station


def daily(client, headers, sid):
    return client.post('/api/reconciliation/daily', headers=headers,
        json={'source_id': sid, 'business_date': '2026-06-01', 'upstream_volume_nm3': 100})


def test_full_day_uses_next_midnight_boundary_and_returns_evidence(client, admin_headers):
    sid, station = setup(client, admin_headers, [
        ('2026-06-01T00:00:00Z', 1000), ('2026-06-01T12:00:00Z', 1050),
        ('2026-06-02T00:00:00Z', 1100),
    ])
    r = daily(client, admin_headers, sid)
    assert r.status_code == 200
    body = r.json()
    assert body['plant_volume_nm3'] == 100
    assert body['verdict'] == 'PASS'
    evidence = body['stations'][0]
    assert evidence['station_id'] == station
    assert evidence['sample_count'] == 3
    assert evidence['volume_nm3'] == 100
    assert evidence['issues'] == []


@pytest.mark.parametrize('points,issue', [
    ([('2026-06-01T12:00:00Z', 1000)], 'INSUFFICIENT_SAMPLES'),
    ([('2026-06-01T00:00:00Z', 1000), ('2026-06-01T12:00:00Z', 1100)], 'INCOMPLETE_DAY'),
    ([('2026-06-01T00:00:00Z', 1000), ('2026-06-01T12:00:00Z', 10), ('2026-06-02T00:00:00Z', 1100)], 'COUNTER_ROLLBACK'),
    ([('2026-06-01T00:00:00Z', 1000), ('2026-06-01T00:00:00Z', 1001), ('2026-06-02T00:00:00Z', 1100)], 'DUPLICATE_TIMESTAMP'),
])
def test_bad_data_never_produces_a_financial_verdict(client, admin_headers, points, issue):
    sid, _ = setup(client, admin_headers, points)
    r = daily(client, admin_headers, sid)
    assert r.status_code == 409
    assert issue in r.json()['detail']['stations'][0]['issues']
    assert 'verdict' not in r.json()


def test_one_missing_station_blocks_entire_source_total(client, admin_headers):
    sid, _ = setup(client, admin_headers, [('2026-06-01T00:00:00Z', 1000), ('2026-06-02T00:00:00Z', 1100)])
    missing = _create_station(client, admin_headers, source_id=sid, code='MS-02')
    r = daily(client, admin_headers, sid)
    assert r.status_code == 409
    evidence = next(s for s in r.json()['detail']['stations'] if s['station_id'] == missing)
    assert 'INSUFFICIENT_SAMPLES' in evidence['issues']
    assert evidence['volume_nm3'] is None


def test_dual_loop_requires_same_observation_interval(client, admin_headers):
    _, station = setup(client, admin_headers, [('2026-06-01T00:00:00Z', 1000), ('2026-06-01T23:00:00Z', 1100)])
    for ts, value in [('2026-06-01T01:00:00Z', 2000), ('2026-06-01T22:00:00Z', 2100)]:
        _post_reading(client, admin_headers, station_id=station, ts=ts, accumulated_volume_nm3=value, source='BACKUP')
    r = client.post('/api/reconciliation/dual-loop', headers=admin_headers,
                    json={'station_id': station, 'business_date': '2026-06-01'})
    assert r.status_code == 409
    assert 'MISALIGNED_LOOPS' in r.json()['detail']['stations'][0]['issues']


def test_excel_import_obeys_same_quality_gate(client, admin_headers):
    setup(client, admin_headers, [('2026-06-01T00:00:00Z', 1000), ('2026-06-01T12:00:00Z', 1100)])
    r = _upload(client, admin_headers, _xlsx([['2026-06-01', 'SRC-001', 100]]))
    assert r.status_code == 200
    assert r.json()['failed'] == 1
    assert r.json()['rows'][0]['verdict'] is None
    assert 'INCOMPLETE_DAY' in r.json()['rows'][0]['error']
    assert 'INCOMPLETE_DAY' in r.json()['rows'][0]['stations'][0]['issues']


def test_seed_contains_complete_yesterday_for_a_reproducible_demo(client, admin_headers, session_factory, monkeypatch):
    from datetime import datetime, timezone
    from backend import seed_data
    sid, station = setup(client, admin_headers, [])
    monkeypatch.setattr(seed_data, '_now', lambda: datetime(2026, 6, 2, 12, tzinfo=timezone.utc))
    with session_factory() as db:
        seed_data._seed_readings(db, {'MS-01': station})
    response = daily(client, admin_headers, sid)
    assert response.status_code == 200
    assert response.json()['plant_volume_nm3'] == 720000
    assert response.json()['stations'][0]['excluded_count'] == 10


def test_excel_nonfinite_value_returns_row_error_instead_of_server_error(client, admin_headers):
    setup(client, admin_headers, [('2026-06-01T00:00:00Z', 1000), ('2026-06-02T00:00:00Z', 1100)])
    response = _upload(client, admin_headers, _xlsx([['2026-06-01', 'SRC-001', 'NaN']]))
    assert response.status_code == 200
    assert response.json()['failed'] == 1
    assert response.json()['rows'][0]['upstream_volume_nm3'] is None


def test_local_midnight_cannot_masquerade_as_utc_day(client, admin_headers):
    sid, _ = setup(client, admin_headers, [
        ('2026-06-01T00:00:00+08:00', 1000), ('2026-06-02T00:00:00+08:00', 1100),
    ])
    assert daily(client, admin_headers, sid).status_code == 409


def test_offset_timestamps_are_normalized_before_sqlite_storage(client, admin_headers):
    sid, _ = setup(client, admin_headers, [
        ('2026-06-01T08:00:00+08:00', 1000), ('2026-06-02T08:00:00+08:00', 1100),
    ])
    response = daily(client, admin_headers, sid)
    assert response.status_code == 200
    assert response.json()['verdict'] == 'PASS'
    assert response.json()['stations'][0]['first_ts'] == '2026-06-01T00:00:00Z'
