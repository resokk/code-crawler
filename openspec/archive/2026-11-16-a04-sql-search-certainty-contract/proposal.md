# Proposal: Разграничение обнаружения SQL и доказанного execution в поиске

## Why
Существующий readers/writers API выдаёт найденные SQL accesses и список executions; потребитель может трактовать отсутствие execution как доказанную запись.

## Goal
Формально различать SQL discovered, construction, execution sink, statement binding и resolved DB target при выдаче API/MCP.

## Scope
- Определить typed output contract: discovery_status, execution_link_status, target_resolution, evidence/certainty отдельно.
- Для бездоказательного SQL сохранить found statement, но выставлять execution_link_status=NOT_ESTABLISHED.
- Для execution sink без восстановленного SQL предоставить execution record с пустым statements и явным coverage.
- Не менять семантику сохранённых UCM relations и не повышать certainty из-за текстового совпадения.
- Обновить docstrings MCP и примеры безопасных ответов агентам.

## Non-goals
Не делать runtime tracing и не считать статический sink доказательством реального выполнения.

## Dependencies
A03 желательно перед новыми поисковыми DTO

## Impacted code
src/code_crawler/search.py; src/code_crawler/server.py; tests/integration/test_structural_search.py; docs/structural-search.md; docs/server.md

## Priority
P1

## Acceptance summary
1. Нет ложного выполнения.
2. Доказанный sink.
3. Неизвестный SQL sink.
4. Различие DB resolution.
