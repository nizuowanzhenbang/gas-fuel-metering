from sqlalchemy import select, update, delete

from backend.models import MeteringReading
from backend.tests.test_reconciliation_quality import setup
from backend.tests.test_reconciliation_router import _post_reading
from backend.tests.test_reconciliation_router import _create_station

URL = '/api/reconciliation/runs'


def create(client, headers):
    sid, station = setup(client, headers, [
        ('2026-06-01T00:00:00Z', 1000), ('2026-06-02T00:00:00Z', 1100)])
    _post_reading(client, headers, station_id=station, ts='2026-06-01T12:00:00Z',
                  accumulated_volume_nm3=900, validity='FAULT')
    response = client.post(URL, headers=headers, json={
        'source_id': sid, 'business_date': '2026-06-01', 'upstream_volume_nm3': 100})
    assert response.status_code == 201, response.text
    return response.json()


def test_archive_replays_frozen_inputs_and_child_preserves_parent(client, admin_headers, session_factory, monkeypatch):
    run = create(client, admin_headers)
    snap = run['snapshot']
    assert snap['result']['plant_volume_nm3'] == 100
    assert snap['result']['stations'][0]['excluded_count'] == 1
    assert snap['stations'][0]['readings'][0]['counter'] == '1000.000'
    assert len(snap['stations'][0]['readings']) == 3
    assert run['created_by'] == 'admin'
    with session_factory() as db:
        end = db.scalars(select(MeteringReading).order_by(MeteringReading.ts.desc())).first()
        end.accumulated_volume_nm3 = 1120
        db.commit()
    from backend.config import get_settings
    from backend.utils import reconciliation
    monkeypatch.setattr(get_settings(), 'business_timezone', 'UTC+08:00')
    monkeypatch.setattr(get_settings(), 'business_day_start_minute', 31)
    monkeypatch.setattr(reconciliation, 'DAILY_TOLERANCE_PCT', 50)
    monkeypatch.setattr(reconciliation, 'FAIL_MULTIPLIER', 1000)
    assert client.get(f"{URL}/{run['id']}/verify", headers=admin_headers).json()['matches'] is True
    child = client.post(f"{URL}/{run['id']}/recalculate", headers=admin_headers, json={})
    assert child.status_code == 201, child.text
    child = child.json()
    assert child['parent_run_id'] == run['id']
    assert child['snapshot']['window'] == snap['window']
    assert child['snapshot']['result']['plant_volume_nm3'] == 120
    assert child['snapshot']['result']['verdict'] == 'FAIL'
    assert child['snapshot']['delta_plant_nm3'] == 20
    assert client.get(f"{URL}/{run['id']}", headers=admin_headers).json() == run
    assert len(client.get(URL, headers=admin_headers).json()) == 2


def test_missing_data_does_not_append_and_old_run_survives_deletion(client, admin_headers, session_factory):
    run = create(client, admin_headers)
    with session_factory() as db:
        db.execute(delete(MeteringReading))
        db.commit()
    response = client.post(f"{URL}/{run['id']}/recalculate", headers=admin_headers, json={})
    assert response.status_code == 409
    assert len(client.get(URL, headers=admin_headers).json()) == 1
    assert client.get(f"{URL}/{run['id']}/verify", headers=admin_headers).json()['matches'] is True


def test_archive_permissions(client, admin_headers, viewer_headers):
    run = create(client, admin_headers)
    assert client.get(URL, headers=viewer_headers).status_code == 200
    assert client.get(f"{URL}/{run['id']}/verify", headers=viewer_headers).status_code == 200
    assert client.post(f"{URL}/{run['id']}/recalculate", headers=viewer_headers, json={}).status_code == 403
    assert client.post(URL, headers=viewer_headers, json={
        'source_id': 1, 'business_date': '2026-06-01', 'upstream_volume_nm3': 100}).status_code == 403
    assert client.get(URL).status_code == 401
    assert client.put(f"{URL}/{run['id']}", headers=admin_headers, json={}).status_code == 405
    assert client.delete(f"{URL}/{run['id']}", headers=admin_headers).status_code == 405


def test_modified_snapshot_is_rejected(client, admin_headers, session_factory):
    from backend.models.reconciliation_runs import ReconciliationRun
    run = create(client, admin_headers)
    altered = run['snapshot']
    altered['upstream_volume_nm3'] = 999
    with session_factory() as db:
        db.execute(update(ReconciliationRun).values(snapshot_json=altered))
        db.commit()
    assert client.get(f"{URL}/{run['id']}/verify", headers=admin_headers).status_code == 409
    assert client.post(f"{URL}/{run['id']}/recalculate", headers=admin_headers, json={}).status_code == 409


def test_upstream_revision_filtering_and_multiple_children(client, admin_headers):
    run = create(client, admin_headers)
    ids = set()
    for upstream in (101, 102):
        response = client.post(f"{URL}/{run['id']}/recalculate", headers=admin_headers,
                               json={'upstream_volume_nm3': upstream})
        assert response.status_code == 201
        child = response.json()
        ids.add(child['id'])
        assert child['snapshot']['result']['upstream_volume_nm3'] == upstream
        assert child['snapshot']['delta_plant_nm3'] == 0
    assert len(ids) == 2
    assert len(client.get(URL, headers=admin_headers, params={'source_id': run['source_id'],
               'business_date': '2026-06-01', 'offset': 1, 'limit': 1}).json()) == 1
    assert client.get(URL, headers=admin_headers, params={'business_date': '2026-06-02'}).json() == []
    assert client.get(URL, headers=admin_headers, params={'limit': 201}).status_code == 422
    assert client.get(f'{URL}/missing', headers=admin_headers).status_code == 404
    assert client.post(f"{URL}/{run['id']}/recalculate", headers=admin_headers,
                       json={'upstream_volume_nm3': 0}).status_code == 422


def test_added_empty_station_blocks_new_run_without_changing_archive(client, admin_headers):
    run = create(client, admin_headers)
    _create_station(client, admin_headers, source_id=run['source_id'], code='MS-02')
    body = {'source_id': run['source_id'], 'business_date': '2026-06-01', 'upstream_volume_nm3': 100}
    assert client.post(URL, headers=admin_headers, json=body).status_code == 409
    assert client.post(f"{URL}/{run['id']}/recalculate", headers=admin_headers, json={}).status_code == 409
    assert len(client.get(URL, headers=admin_headers).json()) == 1
    assert client.get(f"{URL}/{run['id']}/verify", headers=admin_headers).json()['matches'] is True


def test_snapshot_matches_daily_and_survives_source_deletion(client, admin_headers, session_factory):
    from backend.models import GasSource, MeteringStation
    run = create(client, admin_headers)
    daily = client.post('/api/reconciliation/daily', headers=admin_headers, json={
        'source_id': run['source_id'], 'business_date': '2026-06-01', 'upstream_volume_nm3': 100}).json()
    for key, value in run['snapshot']['result'].items():
        assert daily[key] == value
    with session_factory() as db:
        db.execute(delete(MeteringReading))
        db.execute(delete(MeteringStation))
        db.execute(delete(GasSource))
        db.commit()
    assert client.get(f"{URL}/{run['id']}/verify", headers=admin_headers).json()['matches'] is True
    assert client.post(f"{URL}/{run['id']}/recalculate", headers=admin_headers, json={}).status_code == 409


def test_replay_honors_stored_rules_and_rejects_unknown_version():
    import pytest
    from backend.services.reconciliation_archive import replay
    snapshot = {
        'algorithm': {'version': 'daily-volume-v1', 'tolerance_pct': 0.5, 'fail_multiplier': 3.0},
        'window': {'policy': {'timezone': 'UTC', 'start_minute': 0},
                   'start_utc': '2026-06-01T00:00:00Z', 'end_utc': '2026-06-02T00:00:00Z'},
        'upstream_volume_nm3': 100,
        'stations': [{'id': 1, 'readings': [
            {'ts': '2026-06-01T00:00:00Z', 'counter': '1000.000', 'validity': 'VALID'},
            {'ts': '2026-06-02T00:00:00Z', 'counter': '1101.250', 'validity': 'VALID'}]}]}
    assert replay(snapshot)['verdict'] == 'WARN'
    snapshot['algorithm']['fail_multiplier'] = 2.0
    assert replay(snapshot)['verdict'] == 'FAIL'
    snapshot['algorithm']['version'] = 'unknown'
    with pytest.raises(ValueError, match='unsupported'):
        replay(snapshot)
