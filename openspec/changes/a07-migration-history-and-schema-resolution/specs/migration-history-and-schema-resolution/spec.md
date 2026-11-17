# Capability: migration-history-and-schema-resolution

## ADDED Requirements

### Requirement: Historical populated-database upgrade verification
The system MUST verify database migration compatibility on a representative populated PostgreSQL 15 database created with pinned pre-change historical migrations.

#### Scenario: Upgrade the previous release
- GIVEN a populated PG15 instance initialized by the `b5b3f35` migration set, including published UCM facts and archived Evidence
- WHEN the current version's forward-only migration process is run
- THEN it either upgrades without corrupting existing published snapshots, checksums and reader output, or fails with an explicit non-destructive diagnostic; it MUST NOT silently rebuild the data

#### Scenario: Fresh and upgraded schema comparison
- GIVEN separate clean installations using the old-upgraded path and the current fresh path
- WHEN schema inventory, indexes, FKs, functions, triggers and application reads are compared
- THEN expected differences are documented and unexplained structural drift fails acceptance

### Requirement: Migration integrity cannot rely on filename alone
The system MUST record or verify a stable content identity for applied migration SQL without falsely claiming historical provenance.

#### Scenario: Applied file is modified
- GIVEN a migration applied with recorded checksum C1
- WHEN its filename is unchanged but content now has checksum C2
- THEN `db status` and `db migrate` report a mismatch; no pending DDL is applied automatically

#### Scenario: Legacy checksum is unknown
- GIVEN a previously deployed migration was recorded only as filename and application time
- WHEN code upgrades to checksum-aware management
- THEN the result is UNVERIFIED until accepted historical provenance or an explicit administrative reconciliation is recorded; a current Git file hash is not claimed to be the original executed bytes

#### Scenario: Multiple migrations share a numeric prefix
- GIVEN two SQL files both have numeric prefix 0030 but different filenames
- WHEN migrating an existing or fresh DB
- THEN the ordering policy is deterministic and documented; a late-arriving earlier-order migration cannot silently execute in an incompatible sequence

### Requirement: Schema resolution is deterministic
The system MUST apply one documented schema policy consistently to migration metadata, DDL and runtime UCM queries.

#### Scenario: Custom search_path with colliding objects
- GIVEN PostgreSQL role `search_path` includes two writable schemas with same-named UCM objects
- WHEN `db init`, `db status`, or indexed read is executed
- THEN operations either use the explicitly selected schema or fail closed; no accidental table creation/read/write occurs in an unintended schema

#### Scenario: Older public-qualified database
- GIVEN an existing database with UCM tables created explicitly in public
- WHEN unqualified newer queries are executed under the documented supported configuration
- THEN they target the same intended objects, without unexplained shadowing

### Requirement: Failure preserves existing snapshots
A failed upgrade or integrity check MUST not mutate the current published snapshot pointer, archived Evidence, foreign key graph or persistent resolver contexts.

#### Scenario: Integrity mismatch before a pending migration
- GIVEN an existing published snapshot and a mismatched applied migration checksum
- WHEN `db migrate` is invoked
- THEN it fails before executing pending migrations and previously published facts remain readable
