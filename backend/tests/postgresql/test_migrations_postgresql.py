"""Same migration acceptance on PostgreSQL, plus durable archived runs."""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from backend.database import Base
from backend.migrate import upgrade_database, check_database
from backend.models import GasSource, MeteringReading, MeteringStation, ReconciliationRun
from backend.services.reconciliation_archive import archive, verify

# Reuse behavioral tests; conftest supplies an actual PostgreSQL engine.
from backend.tests.test_migrations import (  # noqa: F401
    test_empty_upgrade_and_repeat, test_legacy_data_survives_adoption,
    test_unknown_structure_refused_without_version_write,
    test_unknown_revision_refused, test_startup_check_never_adopts_unversioned,
    test_drift_refused_even_at_head, test_failure_rolls_back_created_schema,
    test_application_startup_gate,
    test_generated_column_refused_before_adoption,
)


def test_archive_survives_adoption_and_transaction_failure(migration_engine):
    # Simulate a populated round-7 database before Alembic adoption.
    Base.metadata.create_all(migration_engine)
    with Session(migration_engine) as db:
        source = GasSource(code='SRC-PG', name='Test', supplier='Synthetic', gas_type='PIPELINE')
        db.add(source)
        db.flush()
        station = MeteringStation(code='MS-PG', name='Test', source_id=source.id,
                                  location='Test', design_pressure_kpa=100,
                                  design_flow_min_nm3h=0, design_flow_max_nm3h=1000)
        db.add(station)
        db.flush()
        for ts, counter in [(datetime(2026, 6, 1, tzinfo=timezone.utc), 1000),
                            (datetime(2026, 6, 2, tzinfo=timezone.utc), 1100)]:
            db.add(MeteringReading(station_id=station.id, ts=ts, accumulated_volume_nm3=counter,
                                  actual_volume_rate_m3h=1, normal_volume_rate_nm3h=1,
                                  pressure_kpa=100, temperature_c=20, validity='VALID', source='PRIMARY'))
        db.commit()
        original = archive(db, source.id, date(2026, 6, 1), 100, 'test')
    upgrade_database(migration_engine)
    migration_engine.dispose()  # New connections; no uncommitted fixture transaction.
    with Session(migration_engine) as db:
        parent = db.get(ReconciliationRun, original['id'])
        verify(parent)
        assert parent.snapshot_sha256 == original['snapshot_sha256']
        assert parent.snapshot_json == original['snapshot']
        end = db.scalars(select(MeteringReading).order_by(MeteringReading.ts.desc())).first()
        end.accumulated_volume_nm3 = 1120
        db.commit()
        child = archive(db, parent.source_id, parent.business_date, 100, 'test', parent)
        assert child['snapshot']['result']['plant_volume_nm3'] == 120
        assert child['parent_run_id'] == original['id']

    def fail_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO reconciliation_runs'):
            raise RuntimeError('injected insert failure')
    event.listen(migration_engine, 'before_cursor_execute', fail_insert)
    try:
        with Session(migration_engine) as db:
            parent = db.get(ReconciliationRun, original['id'])
            with pytest.raises(RuntimeError, match='injected'):
                archive(db, parent.source_id, parent.business_date, 100, 'test', parent)
    finally:
        event.remove(migration_engine, 'before_cursor_execute', fail_insert)
    with Session(migration_engine) as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationRun)) == 2
        verify(db.get(ReconciliationRun, original['id']))
        verify(db.get(ReconciliationRun, child['id']))
    check_database(migration_engine)


@pytest.mark.parametrize('definition', [
    'CREATE UNIQUE INDEX ix_users_username ON users (username DESC)',
    'CREATE UNIQUE INDEX ix_users_username ON users (username) INCLUDE (full_name)',
    'CREATE UNIQUE INDEX ix_users_username ON users (username varchar_pattern_ops)',
])
def test_nonbaseline_index_attributes_refused(migration_engine, definition):
    from sqlalchemy import text, inspect
    Base.metadata.create_all(migration_engine)
    with migration_engine.begin() as conn:
        conn.execute(text('DROP INDEX ix_users_username'))
        conn.execute(text(definition))
    with pytest.raises(RuntimeError, match='Unknown database structure'):
        upgrade_database(migration_engine)
    assert 'alembic_version' not in inspect(migration_engine).get_table_names()


@pytest.mark.parametrize('change', [
    'ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE',
    'ALTER TABLE users ALTER COLUMN id DROP DEFAULT; ALTER TABLE users ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY',
])
def test_column_semantics_refused(migration_engine, change):
    from sqlalchemy import text, inspect
    Base.metadata.create_all(migration_engine)
    with migration_engine.begin() as conn:
        for statement in change.split(';'):
            conn.execute(text(statement))
    with pytest.raises(RuntimeError, match='Unknown database structure'):
        upgrade_database(migration_engine)
    assert 'alembic_version' not in inspect(migration_engine).get_table_names()
