# Proposal: Сквозная bounded-memory индексация

## Why
Analyzer по срезам и staging уже есть, server-side reuse добавлен; validation и источники некоторых адаптеров ещё используют большие модели.

## Target outcome
Сквозная bounded-memory индексация: Ввести ограниченный in-flight budget по количеству entities/bytes, а не только файлов; считать max size per file. Использовать stream API с staged writes и server-side clone unchanged facts без объединения в полный UcmBatch. Гарантировать cross-file references, forward references, deterministic ownership/dependency manifest и source archive consistency. Добавить отмену, повтор и fault injection; memory measurement на incremental/full режимах.

## Scope
- Ввести ограниченный in-flight budget по количеству entities/bytes, а не только файлов; считать max size per file.
- Использовать stream API с staged writes и server-side clone unchanged facts без объединения в полный UcmBatch.
- Гарантировать cross-file references, forward references, deterministic ownership/dependency manifest и source archive consistency.
- Добавить отмену, повтор и fault injection; memory measurement на incremental/full режимах.

## Non-goals
Не переписывать адаптеры, которые уже предоставляют корректные FileAnalysis.

## Dependencies
B02,B03,B04

## Affected code
src/code_crawler/incremental.py; src/code_crawler/source_adapters.py; src/code_crawler/ingestion.py; tests/integration/test_incremental_indexing.py

## Priority
P1
