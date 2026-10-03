"""Real PostgreSQL only. Each test owns a fresh random schema in a test database."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


@pytest.fixture
def migration_engine():
    url = os.environ.get('TEST_POSTGRESQL_URL')
    if not url:
        if os.environ.get('REQUIRE_POSTGRESQL_TESTS') == 'true':
            pytest.fail('TEST_POSTGRESQL_URL is required; no fallback')
        pytest.skip('explicit TEST_POSTGRESQL_URL not provided')
    parsed = make_url(url)
    if parsed.get_backend_name() != 'postgresql' or not (parsed.database or '').endswith('_test'):
        pytest.fail('Use a dedicated PostgreSQL database ending in _test')
    schema = 'gfm_test_' + uuid4().hex
    admin = create_engine(url, poolclass=NullPool)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, poolclass=NullPool, connect_args={'options': f'-csearch_path={schema}'})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            assert schema.startswith('gfm_test_') and len(schema) == 41
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
