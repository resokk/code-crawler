# Proposal: Глобальный каталог потенциальных целей

## Why
Сейчас search только repository-scoped; нет производных каталожных ключей для поиска внешних символов, API, Kafka, BPMN и DB resources.

## Outcome
Глобальный каталог потенциальных целей. Разработать search_discovery_entries с repository_id/snapshot_id, entity_id, kind, qualifier, normalized lookup keys и generation. Проецировать только факты PUBLISHED и сохранять уникальность ключей без требования единственного глобального кандидата. Индексировать symbol FQN+signature, DB identifiers, HTTP route/service, worker/process, reference dataset и Kafka topic; неизвестные типы не выдумывать. Поддержать retire/GC/rollback/generation invalidation без переиндексации несвязанных репозиториев.

## Scope
- Разработать search_discovery_entries с repository_id/snapshot_id, entity_id, kind, qualifier, normalized lookup keys и generation.
- Проецировать только факты PUBLISHED и сохранять уникальность ключей без требования единственного глобального кандидата.
- Индексировать symbol FQN+signature, DB identifiers, HTTP route/service, worker/process, reference dataset и Kafka topic; неизвестные типы не выдумывать.
- Поддержать retire/GC/rollback/generation invalidation без переиндексации несвязанных репозиториев.

## Non-goals
Никаких подтверждённых межрепозиторных рёбер при индексации.

## Dependencies
C01, C03 желательно

## Impacted code
src/code_crawler/migrations/; src/code_crawler/search.py; src/code_crawler/ucm.py; docs/; tests/integration/

## Priority
P1
