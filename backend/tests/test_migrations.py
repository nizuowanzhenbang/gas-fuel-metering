import pytest
from sqlalchemy import create_engine, inspect, text, event

from backend.database import Base
from backend.migrate import upgrade_database, check_database, HEAD


@pytest.fixture
def migration_engine(tmp_path):
    engine = create_engine('sqlite:///' + (tmp_path / 'migration.db').as_posix())
    yield engine
    engine.dispose()


def test_empty_upgrade_and_repeat(migration_engine):
    with pytest.raises(RuntimeError):
        check_database(migration_engine)
    assert upgrade_database(migration_engine) == HEAD
    assert upgrade_database(migration_engine) == HEAD
    assert check_database(migration_engine) == HEAD


@pytest.mark.parametrize('archive_exists', [False, True])
def test_legacy_data_survives_adoption(migration_engine, archive_exists):
    tables = [t for t in Base.metadata.sorted_tables if archive_exists or t.name != 'reconciliation_runs']
    Base.metadata.create_all(migration_engine, tables=tables)
    with migration_engine.begin() as conn:
        conn.execute(text("INSERT INTO users (username,password_hash,full_name,role,is_active,created_at) "
                          "VALUES ('retained','hash','Retained','VIEWER',true,CURRENT_TIMESTAMP)"))
    upgrade_database(migration_engine)
    with migration_engine.connect() as conn:
        assert conn.scalar(text('SELECT username FROM users')) == 'retained'
        assert 'reconciliation_runs' in inspect(conn).get_table_names()


def test_unknown_structure_refused_without_version_write(migration_engine):
    Base.metadata.create_all(migration_engine)
    with migration_engine.begin() as conn:
        conn.execute(text('ALTER TABLE users ADD COLUMN unexpected INTEGER'))
    with pytest.raises(RuntimeError, match='Unknown database structure'):
        upgrade_database(migration_engine)
    assert 'alembic_version' not in inspect(migration_engine).get_table_names()


def test_unknown_revision_refused(migration_engine):
    upgrade_database(migration_engine)
    with migration_engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='future_version'"))
    with pytest.raises(RuntimeError, match='version'):
        upgrade_database(migration_engine)
    with migration_engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == 'future_version'


def test_startup_check_never_adopts_unversioned(migration_engine):
    Base.metadata.create_all(migration_engine)
    with pytest.raises(RuntimeError):
        check_database(migration_engine)
    assert 'alembic_version' not in inspect(migration_engine).get_table_names()


@pytest.mark.parametrize('change', [
    'DROP INDEX ix_users_username',
    'CREATE VIEW unexpected_view AS SELECT username FROM users',
    'CREATE TABLE unrelated (id INTEGER)',
])
def test_drift_refused_even_at_head(migration_engine, change):
    upgrade_database(migration_engine)
    with migration_engine.begin() as conn:
        conn.execute(text(change))
    with pytest.raises(RuntimeError, match='Unknown database structure'):
        upgrade_database(migration_engine)
    with pytest.raises(RuntimeError, match='Unknown database structure'):
        check_database(migration_engine)


def test_failure_rolls_back_created_schema(migration_engine):
    def fail(conn, cursor, statement, parameters, context, executemany):
        if 'CREATE TABLE reconciliation_runs' in statement:
            raise RuntimeError('injected migration failure')
    event.listen(migration_engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            upgrade_database(migration_engine)
    finally:
        event.remove(migration_engine, 'before_cursor_execute', fail)
    assert inspect(migration_engine).get_table_names() == []
    upgrade_database(migration_engine)


def test_direct_alembic_is_refused():
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    with pytest.raises(RuntimeError, match='direct unvalidated'):
        command.upgrade(cfg, 'head')


def test_application_startup_gate(migration_engine, monkeypatch):
    from backend import database
    monkeypatch.setattr(database, 'engine', migration_engine)
    with pytest.raises(RuntimeError):
        database.init_db()
    upgrade_database(migration_engine)
    database.init_db()


def test_generated_column_refused_before_adoption(migration_engine):
    Base.metadata.create_all(migration_engine)
    with migration_engine.begin() as conn:
        conn.execute(text('ALTER TABLE users DROP COLUMN full_name'))
        conn.execute(text('ALTER TABLE users ADD COLUMN full_name VARCHAR(64) GENERATED ALWAYS AS (username) STORED NOT NULL'))
    with pytest.raises(RuntimeError, match='Unknown database structure'):
        upgrade_database(migration_engine)
    assert 'alembic_version' not in inspect(migration_engine).get_table_names()
