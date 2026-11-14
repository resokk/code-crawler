# Proposal: Инкрементальность на реальных Java/Groovy/PLPlus репозиториях

## Why
Per-adapter invalidation реализована, но OpenSpec содержит открытый пункт про реальный mixed-language репозиторий.

## Target outcome
Инкрементальность на реальных Java/Groovy/PLPlus репозиториях: Подготовить версионированный test fixture, представляющий package imports, CFT selectors и Groovy dependencies. Фиксировать список adapter invocations и reuse manifests при изменении Java source/catalog. Проверить транзитивную invalidation связанных языков и отсутствие сброса unrelated facts. Проверить rename/delete, отсутствующие dependencies и untracked files.

## Scope
- Подготовить версионированный test fixture, представляющий package imports, CFT selectors и Groovy dependencies.
- Фиксировать список adapter invocations и reuse manifests при изменении Java source/catalog.
- Проверить транзитивную invalidation связанных языков и отсутствие сброса unrelated facts.
- Проверить rename/delete, отсутствующие dependencies и untracked files.

## Non-goals
Не менять маршрутизацию файлов без подтверждённого дефекта.

## Dependencies
B05 желательно

## Affected code
src/code_crawler/source_adapters.py; src/code_crawler/incremental.py; tests/integration/test_source_adapter_registry.py; docs/source-adapters.md

## Priority
P1
