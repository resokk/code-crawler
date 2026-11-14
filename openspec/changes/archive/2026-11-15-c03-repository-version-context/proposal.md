# Proposal: Выбор согласованного контекста версий репозиториев

## Why
При cross-repo поиске нельзя подбирать произвольные latest versions без deployment/pinned constraints; текущие запросы scoped to one published snapshot.

## Outcome
Выбор согласованного контекста версий репозиториев. Реализовать resolver_contexts с режимами LATEST_INDEXED, PINNED_SNAPSHOTS, DEPLOYMENT_CONTEXT и immutable selection manifest. Для pinned проверять repo ownership, readiness и наличие retained snapshot; для deployment явное mapping service/deploy to snapshot. Разделить выбор версии, разрешение candidate и publication; missing versions и unknown deployments — явная ошибка/неопределённость. Включать context fingerprint в кэш и Evidence path; поддержать pin retention при GC.

## Scope
- Реализовать resolver_contexts с режимами LATEST_INDEXED, PINNED_SNAPSHOTS, DEPLOYMENT_CONTEXT и immutable selection manifest.
- Для pinned проверять repo ownership, readiness и наличие retained snapshot; для deployment явное mapping service/deploy to snapshot.
- Разделить выбор версии, разрешение candidate и publication; missing versions и unknown deployments — явная ошибка/неопределённость.
- Включать context fingerprint в кэш и Evidence path; поддержать pin retention при GC.

## Non-goals
Не модифицировать canonical snapshot и не объявлять одновременно развёрнутыми все latest commits.

## Dependencies
C02 может разрабатываться параллельно

## Impacted code
src/code_crawler/migrations/; src/code_crawler/snapshots.py; src/code_crawler/search.py; docs/; tests/integration/

## Priority
P1
