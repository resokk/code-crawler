# Proposal: Ограниченный графовый обход между репозиториями

## Why
Текущий trace_dependency ограничен одним snapshot и не пересекает deferred ExternalReference.

## Outcome
Ограниченный графовый обход между репозиториями. Обходить локальные Relations внутри snapshot; только при ExternalReference вызывать query-time resolver. Ввести depth, fanout, max nodes, max hops между repos, timeout/cancellation и total result cap. Проводить авторизацию каждого repository scope до перехода; предотвращать циклы и сохранять порядок пути. Для каждого edge и remote hop возвращать source and target snapshot, Evidence, certainty, resolution, truncation.

## Scope
- Обходить локальные Relations внутри snapshot; только при ExternalReference вызывать query-time resolver.
- Ввести depth, fanout, max nodes, max hops между repos, timeout/cancellation и total result cap.
- Проводить авторизацию каждого repository scope до перехода; предотвращать циклы и сохранять порядок пути.
- Для каждого edge и remote hop возвращать source and target snapshot, Evidence, certainty, resolution, truncation.

## Non-goals
Не создавать persistent global materialized graph и не выполнять бесконечный DFS.

## Dependencies
C03,C04,C05

## Impacted code
src/code_crawler/search.py; src/code_crawler/server.py; src/code_crawler/reader.py; tests/integration/; docs/structural-search.md

## Priority
P1
