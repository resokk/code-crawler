# Proposal: Порционная проверка целостности snapshot

## Why
publication.load_snapshot_batch читает все таблицы и восстанавливает полный UcmBatch при validate_snapshot; память растёт с числом фактов.

## Target outcome
Порционная проверка целостности snapshot: Сформировать полный реестр UcmBatch semantic invariants с отображением на проверки SQL/stream. Проверять unique identities, entity types, typed FK, evidence ranges, relation endpoints, scopes, SQL construction/bindings и ORM инварианты порциями. Сохранять validation receipt и READY только по завершении всех проверок в контролируемом транзакционном протоколе. Сопоставить решения старого и нового валидатора на корректных и искусственно повреждённых snapshots; убрать обязательную полную model hydration из readiness.

## Scope
- Сформировать полный реестр UcmBatch semantic invariants с отображением на проверки SQL/stream.
- Проверять unique identities, entity types, typed FK, evidence ranges, relation endpoints, scopes, SQL construction/bindings и ORM инварианты порциями.
- Сохранять validation receipt и READY только по завершении всех проверок в контролируемом транзакционном протоколе.
- Сопоставить решения старого и нового валидатора на корректных и искусственно повреждённых snapshots; убрать обязательную полную model hydration из readiness.

## Non-goals
Не снижать строгость нынешней UcmBatch validation.

## Dependencies
B01; разделить на inventory, references и readiness

## Affected code
src/code_crawler/publication.py; src/code_crawler/ingestion.py; src/code_crawler/ucm.py; tests/integration/test_publication.py; docs/ucm-publication.md

## Priority
P0
