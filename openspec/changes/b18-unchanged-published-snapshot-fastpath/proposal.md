# Proposal: Быстрый no-op при полностью неизменном опубликованном репозитории

**Priority:** P1/P2 — экономия на повторных запусках

## Why
No-change incremental сейчас создаёт новый immutable BUILDING snapshot и server-side клонирует факты. По B01 400-файловый clone занимает ~33.47 с плюс дальнейшая валидация/публикация, хотя content/fingerprint могут быть идентичными. Для частых cron/CI переиндексаций нужен безошибочный, явный fast-path без потери семантики snapshot identity.

## Intended outcome
Сокращение измеренного времени индексации без изменения канонических UCM-фактов, публикации, покрытия, разрешения и Evidence.

## Scope
- Определить строгий equivalence key: repo identity, source fingerprint, commit hash, branch, dirty state, language routing, adapter versions/fingerprints, SQL path budget, catalog/dependency manifest и selected DB schema/connection context.
- Добавить opt-in --reuse-unchanged-publication для CLI/service без смены текущих API default contracts; возвращать REUSED_CURRENT и уже опубликованный snapshot ID, не создавая новый snapshot/job source data.
- Сохранять existing flow, когда хоть один параметр семантики/контекста изменился, source HEAD обновился, content archive невалиден или publication pointer сменился.
- Добавить race-safe проверку publication pointer, managed permissions, retained pins и source fingerprint; при конфликте выполняется обычный CAS/new snapshot, а не произвольное reuse.
- Измерить повторную индексацию неизменённого repо на 400/1000 файлах с SQL schema contexts, сравнить wall/DB I/O и все reader results.

## Non-goals
- Не выполнять no-op для dirty worktree только по commit SHA.
- Не пересоздавать старые Published snapshots для нового commit даже при одинаковых файлах, если commit identity — часть требуемой provenance.
- Не делать reuse сквозь разные repository keys, user scopes или несовместимые analyzer versions.

## Dependencies
B03 and existing incremental planner, snapshot/publication API; B09.

## Affected code
src/code_crawler/cli.py; src/code_crawler/incremental.py; src/code_crawler/snapshots.py; src/code_crawler/jobs.py; tests/integration/test_default_index.py; tests/integration/test_incremental_indexing.py; docs/ucm-incremental.md

## Acceptance
- Измеренная существенная экономия на no-change сценарии и доказанная идентичность reader outputs. Конфликты и изменённые файлы обязаны пройти обычный путь.
