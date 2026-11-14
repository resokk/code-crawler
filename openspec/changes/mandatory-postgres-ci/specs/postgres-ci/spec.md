# PostgreSQL CI

## Requirement: mandatory real database coverage

### Scenario: full hosted run
GIVEN a pull request or main push WHEN CI runs THEN PostgreSQL 15 is provisioned,
all migrations are applied to a clean database, and all unit/integration/regression
tests execute with locked dependencies.

### Scenario: absent database configuration
GIVEN mandatory mode and absent TEST_DATABASE_URL WHEN pytest starts THEN it exits
nonzero instead of skipping PostgreSQL tests.

### Scenario: omitted or skipped integration suite
GIVEN mandatory mode WHEN no integration test is selected or an integration test is
skipped/xfail or the run only collects tests without executing them THEN the check fails.

### Scenario: optional local tests
GIVEN a local run without mandatory mode and without TEST_DATABASE_URL WHEN the
suite runs THEN integration fixtures may skip while unit tests execute normally.

## Requirement: clean generated artifacts

### Scenario: tests mutate generated files
GIVEN a clean checkout WHEN tooling/tests change tracked files or leave new
nonignored generated files THEN CI fails and preserves status/diff diagnostics.

## Requirement: actionable failures

### Scenario: migration or test failure
GIVEN a failing migration/test/lint stage WHEN the job ends THEN available logs,
JUnit, Git drift and PostgreSQL service output are uploaded as a failure artifact.

### Scenario: merge protection
GIVEN main branch rules require the PostgreSQL 15 check WHEN that check fails THEN
GitHub rejects merge. Merely adding the workflow does not configure branch rules.
