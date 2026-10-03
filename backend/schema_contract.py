"""Read-only comparison against frozen, dialect-specific database contracts."""
import json
from pathlib import Path
import warnings

from sqlalchemy import inspect, text
from sqlalchemy.exc import SAWarning


CONTRACTS = Path(__file__).resolve().parent / 'migrations' / 'contracts'


def _validate_serial(connection, table, column):
    quote = connection.dialect.identifier_preparer.quote
    schema = connection.scalar(text('SELECT current_schema()'))
    qualified = quote(schema) + '.' + quote(table)
    owned = connection.execute(text(
        'SELECT c.oid, n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace '
        'WHERE c.oid=pg_get_serial_sequence(:table, :column)::regclass'),
        {'table': qualified, 'column': column}).first()
    referenced = connection.execute(text(
        "SELECT d.refobjid FROM pg_depend d JOIN pg_attrdef a ON a.oid=d.objid "
        "AND d.classid='pg_attrdef'::regclass JOIN pg_attribute v ON v.attrelid=a.adrelid AND v.attnum=a.adnum "
        "JOIN pg_class s ON s.oid=d.refobjid AND s.relkind='S' "
        "WHERE d.refclassid='pg_class'::regclass AND a.adrelid=to_regclass(:table) AND v.attname=:column"),
        {'table': qualified, 'column': column}).scalars().all()
    if (not owned or owned.nspname != schema or owned.relname != f'{table}_{column}_seq'
            or referenced != [owned.oid]):
        raise RuntimeError(f'Unknown database structure: sequence ownership/reference for {table}.{column}')


def describe_schema(connection):
    inspector = inspect(connection)
    result = {}
    for table in sorted(inspector.get_table_names()):
        if table == 'alembic_version':
            continue
        pk = inspector.get_pk_constraint(table)['constrained_columns']
        columns = {}
        for column in inspector.get_columns(table):
            if column.get('computed') is not None or column.get('identity') is not None:
                raise RuntimeError(f'Unknown database structure: generated column {table}.{column["name"]}')
            default = column.get('default')
            if default and column['name'] in pk and str(default).startswith('nextval('):
                _validate_serial(connection, table, column['name'])
                default = '<serial>'
            columns[column['name']] = {
                'type': str(column['type']), 'enum': getattr(column['type'], 'enums', None),
                'timezone': getattr(column['type'], 'timezone', None),
                'nullable': column['nullable'], 'default': default,
            }
        foreign_keys = [
            {'columns': f['constrained_columns'], 'table': f['referred_table'],
             'target': f['referred_columns'], 'schema': f.get('referred_schema'), 'options': f.get('options', {})}
            for f in inspector.get_foreign_keys(table)
        ]
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='Skipped unsupported reflection of expression-based index.*', category=SAWarning)
            reflected = inspector.get_indexes(table)
        for index in reflected:
            if index.get('column_sorting') or any(index.get('dialect_options', {}).values()):
                raise RuntimeError(f'Unknown database structure: index attributes on {table}')
        if connection.dialect.name == 'sqlite':
            quote = connection.dialect.identifier_preparer.quote
            listed = connection.exec_driver_sql(f'PRAGMA index_list({quote(table)})').all()
            if {i[1] for i in listed if i[3] == 'c'} != {i['name'] for i in reflected}:
                raise RuntimeError(f'Unknown database structure: unreflected index on {table}')
            for index in listed:
                keys = connection.exec_driver_sql(f'PRAGMA index_xinfo({quote(index[1])})').all()
                if any(k[1] < 0 or k[3] != 0 or k[4] != 'BINARY' for k in keys if k[5]):
                    raise RuntimeError(f'Unknown database structure: index sorting/collation on {table}')
        indexes = {
            i['name']: {'columns': i['column_names'], 'unique': bool(i['unique']),
                        'expressions': i.get('expressions'),
                        'where': str(i.get('dialect_options', {}).get(f'{connection.dialect.name}_where', ''))}
            for i in reflected
        }
        result[table] = {
            'columns': columns, 'pk': pk,
            'foreign_keys': sorted(foreign_keys, key=lambda item: json.dumps(item, sort_keys=True)),
            'indexes': indexes,
            'unique': sorted([u['column_names'] for u in inspector.get_unique_constraints(table)]),
            'checks': sorted([c['sqltext'] for c in inspector.get_check_constraints(table)]),
        }
    if inspector.get_view_names():
        raise RuntimeError('Unknown database structure: views are not part of the baseline')
    if connection.dialect.name == 'postgresql':
        # SQLAlchemy 2.0 reflection omits some operator-class/index state details.
        unusual = connection.scalar(text(
            "SELECT count(*) FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid "
            "JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_class ix ON ix.oid=i.indexrelid "
            "JOIN pg_am am ON am.oid=ix.relam WHERE n.nspname=current_schema() AND ("
            "am.amname <> 'btree' OR NOT i.indisvalid OR NOT i.indisready OR "
            "i.indnkeyatts <> i.indnatts OR i.indnullsnotdistinct OR "
            "EXISTS (SELECT 1 FROM unnest(i.indoption) v WHERE v <> 0) OR "
            "EXISTS (SELECT 1 FROM unnest(i.indclass) cl JOIN pg_opclass op ON op.oid=cl WHERE NOT op.opcdefault))"))
        if unusual:
            raise RuntimeError('Unknown database structure: PostgreSQL index properties')
        if inspector.get_materialized_view_names():
            raise RuntimeError('Unknown database structure: materialized views')
        triggers = connection.scalar(text("SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                                          "JOIN pg_namespace n ON n.oid=c.relnamespace "
                                          "WHERE NOT t.tgisinternal AND n.nspname=current_schema()"))
    else:
        triggers = connection.scalar(text("SELECT count(*) FROM sqlite_master WHERE type='trigger'"))
    if triggers:
        raise RuntimeError('Unknown database structure: custom triggers')
    return result


def validate_structure(connection, *, allow_legacy=False):
    dialect = connection.dialect.name
    if dialect not in ('sqlite', 'postgresql'):
        raise RuntimeError('Supported databases are SQLite and PostgreSQL')
    expected = json.loads((CONTRACTS / f'{dialect}.json').read_text(encoding='utf-8'))
    actual = describe_schema(connection)
    if allow_legacy and not actual:
        return 'empty'
    if actual == expected:
        return 'current'
    legacy = {name: table for name, table in expected.items() if name != 'reconciliation_runs'}
    if allow_legacy and actual == legacy:
        return 'baseline'
    differences = sorted(name for name in set(actual) | set(expected) if actual.get(name) != expected.get(name))
    raise RuntimeError('Unknown database structure in tables: ' + ', '.join(differences))
