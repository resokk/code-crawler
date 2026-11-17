# Design: Профилирование критического пути индексации

## Current behavior and reason for change
B01 показывает на 400 Java-файлах 37.30 с analyze, 15.76 с transfer, 10.76 с FK и 43.13 с validation, но nested профили не отделяют построение Java catalog, SQL/ORM, повторный обход AST, Pydantic/row conversion, pickle spool, IPC и временные DB операции. После новых Java/COW/parallel изменений прежние цифры уже не отражают текущий SHA.

## Proposed decisions
### D1: Добавить малозатратные фазовые метрики capture, Java catalog build, parse, calls, SQL reco
Добавить малозатратные фазовые метрики capture, Java catalog build, parse, calls, SQL recovery, SQLGlot, ORM, DTO enrichment, UCM normalization, spool serialize/deserialize, staging, transfer, deferred FK, readiness и publication. Вложенные интервалы помечать: их нельзя суммировать.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D2: Показывать CPU wall/user/system, Python allocations/peak RSS, bytes/entities/rows, child-p
Показывать CPU wall/user/system, Python allocations/peak RSS, bytes/entities/rows, child-process CPU/peak memory, IPC bytes/worker startup; не читать исходный текст и не сохранять SQL или секреты в профиле.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D3: Добавить режим детального профилирования с выключенным по умолчанию трейсингом; baseline б
Добавить режим детального профилирования с выключенным по умолчанию трейсингом; baseline без профилирования измерять отдельно из-за накладных расходов.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D4: Сформировать воспроизводимые входы
Сформировать воспроизводимые входы: small, Java SQL path-heavy, catalog-heavy, SQL-dense, 400/1000-file PG15; фиксировать commit SHA и зависимости.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D5: Сохранять machine-readable breakdown/critical path, суммарное время end-to-end и неучтённы
Сохранять machine-readable breakdown/critical path, суммарное время end-to-end и неучтённый остаток; при неполном выполнении явно помечать absent/stopped stage.

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
src/code_crawler/profiling.py; src/code_crawler/performance_baseline.py; src/code_crawler/java_adapter.py; src/code_crawler/incremental.py; src/code_crawler/ingestion.py; docs/performance-baseline.md; tests/test_profiling.py
