# Design: Совместное переиспользование проходов SQL и ORM по Java-методам

## Current behavior and reason for change
В JavaSqlAnalyzer, JavaExecutionAnalyzer и JavaOrmAnalyzer есть собственные обходы методов/flow, включая _recover(... JpaFlow ...) для ORM. Несмотря на COW, один и тот же Java method может обрабатываться в несколько заходов. Разделять можно лишь read-only промежуточные факты, а не сливать разные семантики SQL и JPA.

## Proposed decisions
### D1: Добавить per-method tracer числа _recover visits, state clones, SQL/ORM dispatches и CPU; 
Добавить per-method tracer числа _recover visits, state clones, SQL/ORM dispatches и CPU; выбрать один подтверждённый hotspot method-heavy fixture.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D2: Выделить immutable shared inputs (method AST boundary, symbol/scope lookup, constant env, 
Выделить immutable shared inputs (method AST boundary, symbol/scope lookup, constant env, resolved API classification) из анализа SQL и JPA без объединения mutable state machines.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D3: Пересчитать downstream SQL construction/execution/ORM только из проверенного intermediate 
Пересчитать downstream SQL construction/execution/ORM только из проверенного intermediate summary; сохранить SQL path budget (default 256) и отдельные parser statuses.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D4: Проверить одинаковые normalized UCM entities, certainty, unresolved candidates, path overf
Проверить одинаковые normalized UCM entities, certainty, unresolved candidates, path overflow report и determinism full/incremental.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D5: Включить feature flag для сравнения и быстрого rollback; не делать оптимизацию, если профи
Включить feature flag для сравнения и быстрого rollback; не делать оптимизацию, если профили не дают выигрыша.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

## Compatibility, resource boundaries and recovery
- All changes MUST preserve stable UCM IDs, normalized facts, Evidence, SourceAnalysis and SQL certainty; no change in result is acceptable solely for speed.
- If analyzer/profile/normalization semantics change, bump relevant version and invalidate only affected adapter results. Scheduling, profiling and CLI tuning alone must not force reindex.
- Avoid unbounded new caches; define strict limits in entries/bytes/inflight work and clean up after cancel/crash.
- Do not reveal SQL/source secrets in logs/profiles. PostgreSQL 15 integration and rollback tests required for storage changes.
- Compare against baseline using pinned fixture, environment, code/dependency versions, wall/CPU, process RSS, PostgreSQL I/O/WAL and canonical digest.

## Failure behavior
On error, no partial canonical snapshot is published. If a proposed optimization causes slowdowns on verified fixtures, keep a measured fallback and do not switch default behavior.

## Files
src/code_crawler/java_sql.py; src/code_crawler/java_execution.py; src/code_crawler/java_orm.py; src/code_crawler/jpa_flow.py; src/code_crawler/java_adapter.py; tests/test_java_sql_cow.py; tests/test_java_orm.py
