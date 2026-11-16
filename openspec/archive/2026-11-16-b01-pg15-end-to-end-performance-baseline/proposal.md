# Proposal: Воспроизводимый baseline производительности PG15

## Why
В проекте есть замеры на 402 Java-файлах и 141424 сущностях, но нет контролируемого end-to-end baseline на актуальном SHA и большом snapshot.

## Target outcome
Воспроизводимый baseline производительности PG15: Зафиксировать версии PG15, Python, окружение, RAM/CPU, work_mem/shared_buffers, тип workload и commit SHA. Раздельно измерить capture, prepare, analyze, stage, transfer/FK, validation, publication, GC и reader queries. Собрать серии на 400, 1000 файлах и >1 млн UCM entities; failures и OOM документировать как результат, не скрывать. Сохранить RAM RSS, IO, WAL, запросы EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON), stats и воспроизводимый fixture generator.

## Scope
- Зафиксировать версии PG15, Python, окружение, RAM/CPU, work_mem/shared_buffers, тип workload и commit SHA.
- Раздельно измерить capture, prepare, analyze, stage, transfer/FK, validation, publication, GC и reader queries.
- Собрать серии на 400, 1000 файлах и >1 млн UCM entities; failures и OOM документировать как результат, не скрывать.
- Сохранить RAM RSS, IO, WAL, запросы EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON), stats и воспроизводимый fixture generator.

## Non-goals
Никаких production SLO без измерений.

## Dependencies
A01 желательно

## Affected code
src/code_crawler/query_benchmark.py; docs/query-indexes.md; docs/benchmarks/; tests/integration/test_query_benchmark_storage.py

## Priority
P0
