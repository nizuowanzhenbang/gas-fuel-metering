"""Maintenance-window schema upgrade/check. Application writers must be stopped."""
import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from .schema_contract import validate_structure

HEAD = '0002_archive'
BASELINE = '0001_baseline'


def _revision(connection):
    inspector = inspect(connection)
    if 'alembic_version' not in inspector.get_table_names():
        return None
    columns = inspector.get_columns('alembic_version')
    if (len(columns) != 1 or columns[0]['name'] != 'version_num'
            or str(columns[0]['type']) != 'VARCHAR(32)' or columns[0]['nullable']
            or columns[0].get('default') is not None
            or inspector.get_pk_constraint('alembic_version')['constrained_columns'] != ['version_num']
            or inspector.get_indexes('alembic_version') or inspector.get_unique_constraints('alembic_version')
            or inspector.get_foreign_keys('alembic_version') or inspector.get_check_constraints('alembic_version')):
        raise RuntimeError('Unknown version table structure')
    rows = connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
    if len(rows) != 1 or rows[0] not in (HEAD, BASELINE):
        raise RuntimeError('Unknown or incomplete database version; no changes made')
    return rows[0]


def _check(connection):
    if _revision(connection) != HEAD:
        raise RuntimeError('Database version is not current; run python -m backend.migrate upgrade')
    validate_structure(connection)
    return HEAD


def check_database(connectable):
    if isinstance(connectable, Connection):
        return _check(connectable)
    if connectable.dialect.name == 'sqlite':
        filename = connectable.url.database
        if filename and filename != ':memory:' and not Path(filename).exists():
            raise RuntimeError('Database is absent; run python -m backend.migrate upgrade')
    with connectable.connect() as connection:
        return _check(connection)


def upgrade_database(engine):
    with engine.connect() as connection:
        try:
            if connection.dialect.name == 'sqlite':
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            elif connection.dialect.name == 'postgresql':
                connection.begin()
                connection.execute(text('SELECT pg_advisory_xact_lock(1789324102)'))
            else:
                raise RuntimeError('Supported databases are SQLite and PostgreSQL')
            revision = _revision(connection)
            kind = validate_structure(connection, allow_legacy=revision is None or revision == BASELINE)
            if revision == BASELINE and kind != 'baseline':
                raise RuntimeError('Database structure does not match baseline version')
            config = Config()
            config.set_main_option('script_location', str(Path(__file__).resolve().parent / 'migrations'))
            config.attributes.update(connection=connection, preflight_passed=True)
            if revision is None and kind in ('baseline', 'current'):
                command.stamp(config, BASELINE if kind == 'baseline' else HEAD)
            command.upgrade(config, HEAD)
            _check(connection)
            connection.commit()
            return HEAD
        except Exception:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['upgrade', 'check'])
    args = parser.parse_args()
    from .database import engine
    try:
        result = upgrade_database(engine) if args.operation == 'upgrade' else check_database(engine)
        print(f'Database {args.operation} passed: {result}')
    except RuntimeError as exc:
        parser.exit(1, f'{exc}\n')
    except SQLAlchemyError:
        parser.exit(1, 'Database operation failed; inspect connection/schema in a protected session.\n')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
