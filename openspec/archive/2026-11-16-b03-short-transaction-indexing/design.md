# Design: Сокращение времени транзакции при индексации

## Background
index_incremental начинает транзакцию до CPU анализа каждого _SLICE, затем держит её на staging, cloning и архивировании.

## Architecture decisions
### 1. Разделить immutable source capture/CPU analysis и стадии транзакционной записи; выбрать spool/staging с ограниченной памятью.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Обеспечить snapshot input fingerprint и повторную verify перед фиксацией staged данных.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Переиспользованные facts клонировать из того же immutable baseline при CAS publication, без long-running repo lock.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Обеспечить idempotent cleanup after crash и работу concurrent indexing jobs.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/incremental.py; src/code_crawler/ingestion.py; src/code_crawler/snapshots.py; tests/integration/test_incremental_indexing.py

## Dependencies
B01; учитывать B02/B05

## Concrete implementation

Analysis, strict FileAnalysis recheck and COPY-row normalization are completed
before the write transaction. Rows/ownership/references/explicit dependencies are
spooled one slice at a time to a private anonymous TemporaryFile. Pickle is used
only as internal transport for this process's normalized wire rows; external
pickle paths/bytes are never accepted. The OS closes/unlinks the file on process
exit, so no persistent spool retention or crash janitor is required. Disk-full
and corrupt/read/write errors fail before publication; no resumable checkpoint.

A shared session advisory lease pins the selected immutable baseline, without an
open read transaction/MVCC snapshot or repository row lock. Acquisition rechecks
presence after the lease and handles cancellation without releasing another
owner's lock count. The index result retains the same base ID for publication CAS.

A preallocated snapshot UUID is used in normalized rows; creation occurs only in
the write transaction. COPY, cloning, archive, manifests and FK flush remain one
atomic transaction. Explicit dependencies use a temporary table instead of an
all-slices Python set. Worktree verification runs before writing and after archive/
FK checks immediately before commit. Captured bytes/catalogs and the one-file
worst case are not bounded by this change; B05 remains separate. No migration.

IncrementalResult adds preparation_seconds, write_transaction_seconds and
spool_bytes with backward-compatible defaults. Opt-in transaction_benchmark uses
a fresh generated Java/SQL fixture and disposable PG15 DB, samples xact_start,
records callbacks inside transactions/RSS/settings, validates the snapshot and
hashes normalized canonical facts. Benchmark failures drop only their own DB.
