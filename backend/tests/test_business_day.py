from datetime import date, datetime, timezone
import pytest
from backend.config import Settings, get_settings
from backend.services.metering_quality import day_window
from backend.tests.test_reconciliation_quality import setup
from backend.tests.test_upload_router import _xlsx, _upload

@pytest.fixture
def policy(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'business_timezone', 'UTC+08:00')
    monkeypatch.setattr(settings, 'business_day_start_minute', 30)


def test_shifted_window_and_adjacent_day(policy):
    start, end = day_window(date(2026, 6, 1))
    assert start.isoformat() == '2026-05-31T16:30:00+00:00'
    assert end == day_window(date(2026, 6, 2))[0]
    assert (end-start).total_seconds() == 86400


@pytest.mark.parametrize('values', [{'business_timezone':'America/New_York'}, {'business_day_start_minute':-1}, {'business_day_start_minute':1440}])
def test_invalid_policy_rejected(values):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


def test_daily_excel_and_scanner_share_policy(policy, client, admin_headers, session_factory, monkeypatch):
    from backend import scheduler
    from backend.tests.test_reconciliation_router import _post_reading
    sid, station = setup(client, admin_headers, [('2026-05-31T16:30:00Z',1000),('2026-06-01T16:30:00Z',1100)])
    for ts, value in [('2026-05-31T16:30:00Z',2000),('2026-06-01T16:30:00Z',2200)]:
        _post_reading(client, admin_headers, station_id=station, ts=ts, accumulated_volume_nm3=value, source='BACKUP')
    r = client.post('/api/reconciliation/daily', headers=admin_headers, json={'source_id':sid,'business_date':'2026-06-01','upstream_volume_nm3':100})
    assert r.status_code == 200, r.text
    upload = _upload(client, admin_headers, _xlsx([['2026-06-01','SRC-001',100]])).json()
    assert upload['rows'][0]['window'] == r.json()['window']
    assert r.json()['window']['start_utc'] == '2026-05-31T16:30:00Z'
    assert upload['rows'][0]['plant_volume_nm3'] == 100
    monkeypatch.setattr(scheduler,'SessionLocal',session_factory)
    # Before June 3 local cutoff, most recently completed day is June 1.
    monkeypatch.setattr(scheduler,'_now',lambda:datetime(2026,6,2,16,29,tzinfo=timezone.utc))
    emitted=[]
    monkeypatch.setattr(scheduler,'emit_alert',lambda *args, **kw:emitted.append(kw))
    assert scheduler.scan_yesterday_dual_loop() == 1
    assert emitted[0]['payload_json']['window'] == r.json()['window']

@pytest.mark.parametrize('minute,now,expected', [
    (480,'2026-06-02T00:00:00+00:00','2026-06-01'),
    (480,'2026-06-01T23:59:59+00:00','2026-05-31'),
    (1439,'2026-06-01T16:04:00+00:00','2026-05-31'),
])
def test_latest_complete_day_at_cutover(minute,now,expected):
    from backend.services.business_day import BusinessDayPolicy
    policy = BusinessDayPolicy(timezone='UTC+08:00', start_minute=minute)
    assert policy.latest_completed_date(datetime.fromisoformat(now)).isoformat() == expected


def test_adjacent_days_share_counter_but_not_volume(policy,client,admin_headers):
    sid,_=setup(client,admin_headers,[('2026-05-31T16:30:00Z',1000),('2026-06-01T16:30:00Z',1100),('2026-06-02T16:30:00Z',1250)])
    volumes=[]
    for day,upstream in [('2026-06-01',100),('2026-06-02',150)]:
        response=client.post('/api/reconciliation/daily',headers=admin_headers,json={'source_id':sid,'business_date':day,'upstream_volume_nm3':upstream})
        assert response.status_code == 200
        volumes.append(response.json()['plant_volume_nm3'])
    assert volumes == [100,150]
    assert sum(volumes) == 250

@pytest.mark.parametrize('minute', [31,1439])
def test_seed_covers_non_five_minute_cutoff(policy,client,admin_headers,session_factory,monkeypatch,minute):
    from backend import seed_data
    from backend.services.business_day import current_policy
    monkeypatch.setattr(get_settings(),'business_day_start_minute',minute)
    now=datetime(2026,6,2,16,0,tzinfo=timezone.utc)
    monkeypatch.setattr(seed_data,'_now',lambda:now)
    sid,station=setup(client,admin_headers,[])
    with session_factory() as db:
        seed_data._seed_readings(db,{'MS-01':station})
    day=current_policy().latest_completed_date(now)
    response=client.post('/api/reconciliation/daily',headers=admin_headers,json={'source_id':sid,'business_date':day.isoformat(),'upstream_volume_nm3':720000})
    assert response.status_code == 200, response.text
    assert response.json()['plant_volume_nm3'] == 720000
