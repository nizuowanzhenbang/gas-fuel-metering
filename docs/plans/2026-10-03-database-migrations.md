# Controlled database migration

Goal: preserve source and archived reconciliation data while moving known unversioned schemas to a frozen revision chain. Unknown structures fail before modification. Application startup checks the revision instead of writing DDL.

Architecture: Alembic 0001 freezes the pre-archive tables, 0002 adds the archive table. Upgrade accepts empty schemas, exact 0001 legacy schemas, or exact 0002 unversioned schemas. Compare frozen dialect contracts (columns/types/nullability/defaults/keys/indexes and unsupported objects), then stamp/upgrade in one transaction. Serialize maintenance commands with SQLite BEGIN IMMEDIATE / PostgreSQL advisory transaction lock; stop application writers during upgrades. No automatic destructive downgrade.

Implementation plan (inline execution):

- [x] Red tests for empty upgrade, populated legacy adoption, archive adoption, repeated upgrade, unknown schema refusal and read-only startup check.
- [x] Frozen Alembic revisions/contracts, protected upgrade/check CLI, startup/seed/Compose instructions.
- [x] Explicit TEST_POSTGRESQL_URL fixture with independent prefixed schema; repeat migration contract and archive persistence/rollback tests across transactions; no SQLite fallback in PostgreSQL job.
- [ ] Local regression, separate PostgreSQL CI service job, independent review, push draft stacked PR and rollback tag; final CI evidence.

Acceptance: old archive digest and replay unchanged after adoption and new engine/session; valid child commits persist, an injected insert failure leaves no row; unknown schema unchanged; direct unvalidated Alembic invocation refused. SQLite regression is not PostgreSQL proof. Database restore to backup is documented but not claimed as rehearsed in this round.

Source: [Alembic connection sharing and stamping](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands), checked 2026-10-03.
