# Mandatory PostgreSQL CI

Run the entire regression/unit/integration suite against PostgreSQL 15 on every
PR and main push. Missing test DB, omitted/skipped integration coverage, migration
failure or generated working-tree drift must fail the check. Preserve optional
local integration runs and upload actionable failure reports. No production schema
or runtime analyzer changes.
