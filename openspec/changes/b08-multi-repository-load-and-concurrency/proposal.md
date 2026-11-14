# Proposal: Нагрузочная проверка 100+ независимых репозиториев

## Why
Цель системы — сотни репозиториев; текущие tests преимущественно про один snapshot/repository.

## Target outcome
Нагрузочная проверка 100+ независимых репозиториев: Создать workload генератор с 100+ repo keys, смешанными языками, конфликтами FQN и DB names. Нагрузить parallel ingest, publication CAS, reader queries и concurrent GC с ограниченными DB connections. Измерить P50/P95 reader latency, throughput indexing, lock waits, memory, WAL/disk и failure recovery. Проверить fairness jobs, tenant/repository isolation и отсутствие межрепозиторных FK.

## Scope
- Создать workload генератор с 100+ repo keys, смешанными языками, конфликтами FQN и DB names.
- Нагрузить parallel ingest, publication CAS, reader queries и concurrent GC с ограниченными DB connections.
- Измерить P50/P95 reader latency, throughput indexing, lock waits, memory, WAL/disk и failure recovery.
- Проверить fairness jobs, tenant/repository isolation и отсутствие межрепозиторных FK.

## Non-goals
Не реализовывать заранее глобальные cross-repo links.

## Dependencies
B01,B02,B03,B04

## Affected code
src/code_crawler/jobs.py; src/code_crawler/publication.py; src/code_crawler/query_benchmark.py; tests/integration/; docs/benchmarks/

## Priority
P1
