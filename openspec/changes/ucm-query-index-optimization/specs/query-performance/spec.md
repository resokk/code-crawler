# Query performance

## Requirement: no mandatory full scans

GIVEN a snapshot with over 100k entities WHEN any structural search query runs
THEN its plan contains no sequential scan of ucm_entities, ucm_symbols,
ucm_relations, ucm_sql_executions, ucm_data_accesses or ucm_sql_access_names.

## Requirement: results unchanged

GIVEN the rewritten queries WHEN the structural search test suite runs THEN all
results are identical to those before the change.

## Requirement: bounded ingest cost

GIVEN the new indexes WHEN the load set is indexed THEN total indexing time does
not measurably increase.

## Requirement: recorded baseline

GIVEN the change WHEN it is complete THEN latency before/after, index sizes and the
measurement conditions are documented.

## Requirement: selective typed incoming lookup

GIVEN a published snapshot with many unrelated relations and a selectively targeted
entity WHEN the typed reader requests incoming relations THEN it locates resolved
targets and resolution candidates through their indexed ID sets rather than
filtering the entire snapshot, while preserving snapshot scope, uncertainty,
deterministic ordering, kind filters and page truncation.

## Requirement: reproducible PostgreSQL 15 measurements

GIVEN a dedicated PostgreSQL 15 admin server WHEN the benchmark runs THEN it uses
an isolated disposable database, compares identical API results before and after
query-index migrations, records actual plans and committed ingestion separately,
and drops only its own database even if a query fails.
