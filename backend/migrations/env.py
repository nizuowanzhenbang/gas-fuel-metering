from alembic import context

connection = context.config.attributes.get('connection')
if connection is None or not context.config.attributes.get('preflight_passed'):
    raise RuntimeError('Use python -m backend.migrate upgrade; direct unvalidated migration is disabled')
context.configure(connection=connection, transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
