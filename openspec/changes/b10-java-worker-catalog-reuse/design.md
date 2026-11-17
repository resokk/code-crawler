# Design: Снижение повторного построения Java-каталога в subprocess

## Current behavior and reason for change
В java_parallel._worker_main каждый spawn-процесс вызывает _build_analyzer(config.sources), повторно строя каталог всего репозитория. В catalog-heavy benchmark 32 файла: 1 worker — 6.14 с/214 МиБ суммарного RSS, 2 workers — 8.81 с/539 МиБ, 4 — 12.22 с/717 МиБ. Запуск 1 worker должен остаться baseline.

## Proposed decisions
### D1: Добавить измеряемый сериализуемый компактный catalog snapshot из immutable declaration/sym
Добавить измеряемый сериализуемый компактный catalog snapshot из immutable declaration/symbol/signature/owner/URI lookup, исключив AST Node/Tree, DB connection, callbacks и Pydantic facts вне нужного профиля.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D2: Пересылать/подключать каталог к worker один раз при запуске, без повторного полного постро
Пересылать/подключать каталог к worker один раз при запуске, без повторного полного построения в каждом процессе; безопасно допускать минимальный локальный parse AST для обрабатываемого файла, если он нужен анализатору.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D3: Выбрать transport после замера (memory mapped read-only data или bounded serialized blob/p
Выбрать transport после замера (memory mapped read-only data или bounded serialized blob/pipe). Зафиксировать версию layout, hashes входных source bytes и fingerprint анализа; malformed/old version отклонять.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D4: Соблюдать owner и lifecycle ресурсов
Соблюдать owner и lifecycle ресурсов: worker termination/cancel/process crash не оставляет временные файлы, пароли или file descriptors, и не меняет published UCM.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D5: Сравнить startup, total wall/CPU и сумму RSS parent+children для 1/2/4 workers на catalog-
Сравнить startup, total wall/CPU и сумму RSS parent+children для 1/2/4 workers на catalog-heavy и SQL-heavy fixtures.

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
src/code_crawler/java_parallel.py; src/code_crawler/java_adapter.py; src/code_crawler/java_catalog.py; tests/test_java_parallel.py; tests/integration/test_parallel_preparation.py; docs/parallel-snapshot-preparation.md
