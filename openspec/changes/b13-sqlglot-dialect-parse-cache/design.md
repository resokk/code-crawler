# Design: Безопасный кэш SQLGlot разбора одинаковых запросов

## Current behavior and reason for change
JavaSemanticAnalyzer.semantic_constructions разбирает SQL constructions через SQLGlot. Многие SQL/JPQL конструкции могут повторяться в разных файлах и методах, но ratio уникальных запросов и время парсинга не измерены. Повторная SQLGlot parse работа — гипотеза, требующая профильного подтверждения.

## Proposed decisions
### D1: Подсчитать total SQL parse attempts, distinct exact texts, parse errors и CPU SQLGlot отде
Подсчитать total SQL parse attempts, distinct exact texts, parse errors и CPU SQLGlot отдельно по dialect/version/parse options; не записывать SQL text или его raw hash в общий monitoring.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D2: При подтверждённых дублях реализовать bounded invocation-local LRU для результата разбора 
При подтверждённых дублях реализовать bounded invocation-local LRU для результата разбора или нормализованного immutable summary; ключ учитывает SQL text bytes, dialect, SQLGlot version и parser options.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D3: Не шарить mutable sqlglot
Не шарить mutable sqlglot.Expression AST между построителями, которые модифицируют узлы; возвращать безопасную копию либо immutable model только при доказанной эквивалентности.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D4: Отдельно кэшировать non-success parse diagnostics без сокрытия SourceRange/варианта/парсин
Отдельно кэшировать non-success parse diagnostics без сокрытия SourceRange/варианта/парсинг-статуса; подтверждать partial variants без DataAccess.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D5: Зафиксировать cache hit/miss/size/eviction и сравнить synthetic duplicate-heavy и mostly-u
Зафиксировать cache hit/miss/size/eviction и сравнить synthetic duplicate-heavy и mostly-unique SQL fixtures.

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
src/code_crawler/java_semantic.py; src/code_crawler/sql_semantic.py; src/code_crawler/jpql.py; tests/test_sql_semantics.py; tests/test_java_semantic.py; docs/sql-semantics.md
