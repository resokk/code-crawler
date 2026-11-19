# Design: Адаптивное распределение Java-файлов по процессам

## Current behavior and reason for change
java_parallel.JavaProcessPool.analyze() делит очередные 64 исходника на равные contiguous groups. Один тяжёлый SQL-метод может занять дольше всей группы; на маленьких и catalog-heavy fixtures multiprocessing медленнее. Опция --analysis-workers N уже есть и default=1; задача не должна дублировать её.

## Proposed decisions
### D1: Определить дешёвый, безопасный cost estimate для файла (размер, количество methods, SQL ca
Определить дешёвый, безопасный cost estimate для файла (размер, количество methods, SQL candidates/paths по текущему parser catalog) без повторного полного SQL анализа.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D2: Добавить deterministic weighted scheduling при N>1
Добавить deterministic weighted scheduling при N>1: ограничение задач/bytes in-flight, фиксированный canonical output order независимо от completion order, no prefetch будущих snapshot slices.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D3: Не выбирать автоматически больше CPU, чем разрешает явная настройка, cgroup CPU/memory bud
Не выбирать автоматически больше CPU, чем разрешает явная настройка, cgroup CPU/memory budget; для малых workloads выполнить в parent sequential path без создания subprocess pool (opt-in adaptive).

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D4: Добавить метрики per-worker busy/idle/wall, queue skew, startup overhead и fallback; парам
Добавить метрики per-worker busy/idle/wall, queue skew, startup overhead и fallback; параметры стратегии не включать в analysis fingerprint, пока normalized facts не меняются.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D5: Сравнить balanced/imbalanced CPU-heavy и catalog-heavy fixtures при workers=1/2/4, с синте
Сравнить balanced/imbalanced CPU-heavy и catalog-heavy fixtures при workers=1/2/4, с синтетическим тяжёлым и лёгкими файлами.

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
src/code_crawler/java_parallel.py; src/code_crawler/java_adapter.py; src/code_crawler/cli.py; src/code_crawler/parallel_benchmark.py; tests/test_java_parallel.py; docs/parallel-snapshot-preparation.md
