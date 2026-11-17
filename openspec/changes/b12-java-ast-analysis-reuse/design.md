# Design: Повторное использование Java AST и промежуточного анализа

## Current behavior and reason for change
JavaSemanticAnalyzer.analysis и другие подклассы вызывают super().analysis, а HTTP/Java binding catalogs выполняют дополнительные обходы. Наличие AST/cache внутри Java catalog не доказывает отсутствие повторной работы между passes; сначала нужен tracer B09 для конкретных вызовов parse/extractor и IR.

## Proposed decisions
### D1: Инструментировать числа Tree-sitter parse calls, symbol extraction и traversal passes отде
Инструментировать числа Tree-sitter parse calls, symbol extraction и traversal passes отдельно для prepare, Java full analysis, HTTP/Kafka/BPMN enrichment.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D2: Там, где профилем подтверждена повторная работа, передавать immutable per-file parse/symbo
Там, где профилем подтверждена повторная работа, передавать immutable per-file parse/symbol scope lookup внутри одного worker/analysis invocation без долгоживущего кеширования Node по repository.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D3: Кэшировать только результаты с зависимостями source_sha256, catalog fingerprint, analyzer 
Кэшировать только результаты с зависимостями source_sha256, catalog fingerprint, analyzer profile и версией parser, не включая конфиденциальные сырые исходники в shared cache.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D4: Обеспечить clear-on-file/end-of-slice и после отмены; сохранить exact SourceRange/Evidence
Обеспечить clear-on-file/end-of-slice и после отмены; сохранить exact SourceRange/Evidence/AST diagnostic behavior.

Implementation should reuse existing canonical UCM and a bounded worker/local contract; add instrumentation or benchmark first where the speed-up is hypothetical. Preserve exact source coordinates, immutable published snapshot state and deterministic versioned analysis outputs.

### D5: Сравнить parser CPU, file memory и semantic digest до/после на Java + ORM, duplicated FQN 
Сравнить parser CPU, file memory и semantic digest до/после на Java + ORM, duplicated FQN и malformed fixtures.

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
src/code_crawler/java_adapter.py; src/code_crawler/java_symbols.py; src/code_crawler/java_calls.py; src/code_crawler/java_semantic.py; src/code_crawler/java_database.py; src/code_crawler/java_orm.py; tests/test_java_symbols.py; tests/test_java_calls.py
