# Proposal: Кэш query-time разрешений с инвалидацией

## Why
Повторные lookup across hundreds repos затратны; кэш не должен выдавать устаревшие результаты после смены published generation.

## Outcome
Кэш query-time разрешений с инвалидацией. Задать cache key: ExternalReference selector hash, context fingerprint, discovery generation и resolver algorithm version. Хранить candidates и resolution с TTL/limits, provenance и однозначными reasons. При изменении publication pointers или generation инвалидация должна вытекать из ключей; старые кэши не показывать. Добавить bounded cache size, instrumentation hit/miss, race-safe generation reads.

## Scope
- Задать cache key: ExternalReference selector hash, context fingerprint, discovery generation и resolver algorithm version.
- Хранить candidates и resolution с TTL/limits, provenance и однозначными reasons.
- При изменении publication pointers или generation инвалидация должна вытекать из ключей; старые кэши не показывать.
- Добавить bounded cache size, instrumentation hit/miss, race-safe generation reads.

## Non-goals
Не делать resolver_cache источником истины для UCM и не зависеть от глобального массового обновления графа.

## Dependencies
C02,C03,C04

## Impacted code
src/code_crawler/migrations/; src/code_crawler/search.py; src/code_crawler/publication.py; tests/integration/; docs/

## Priority
P1
