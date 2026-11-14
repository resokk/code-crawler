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
