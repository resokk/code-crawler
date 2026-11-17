# Proposal: Сокращение времени транзакции при индексации

## Why
index_incremental начинает транзакцию до CPU анализа каждого _SLICE, затем держит её на staging, cloning и архивировании.

## Target outcome
Сокращение времени транзакции при индексации: Разделить immutable source capture/CPU analysis и стадии транзакционной записи; выбрать spool/staging с ограниченной памятью. Обеспечить snapshot input fingerprint и повторную verify перед фиксацией staged данных. Переиспользованные facts клонировать из того же immutable baseline при CAS publication, без long-running repo lock. Обеспечить idempotent cleanup after crash и работу concurrent indexing jobs.

## Scope
- Разделить immutable source capture/CPU analysis и стадии транзакционной записи; выбрать spool/staging с ограниченной памятью.
- Обеспечить snapshot input fingerprint и повторную verify перед фиксацией staged данных.
- Переиспользованные facts клонировать из того же immutable baseline при CAS publication, без long-running repo lock.
- Обеспечить idempotent cleanup after crash и работу concurrent indexing jobs.

## Non-goals
Не терять единую атомарную публикацию и контроль worktree fingerprint.

## Dependencies
B01; учитывать B02/B05

## Affected code
src/code_crawler/incremental.py; src/code_crawler/ingestion.py; src/code_crawler/snapshots.py; tests/integration/test_incremental_indexing.py

## Priority
P1
