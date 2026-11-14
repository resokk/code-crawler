# Capability: required-main-ci

## ADDED Requirements

### Requirement: Required check
The system MUST зафиксировать стабильное check name PostgreSQL 15 и имя workflow CI.

#### Scenario: Required check
- GIVEN PR с красным PostgreSQL 15
- WHEN автор пытается merge
- THEN GitHub отклоняет merge.

### Requirement: Missing status
The system MUST описать создание branch ruleset/branch protection для main с required status check и запретом bypass по умолчанию.

#### Scenario: Missing status
- GIVEN PR без required check
- WHEN автор пытается merge
- THEN GitHub отклоняет merge.

### Requirement: Реальный success
The system MUST проверить правило через контролируемый тестовый PR (не мержить).

#### Scenario: Реальный success
- GIVEN PR со всеми успешно завершёнными required checks
- WHEN merge проверяется
- THEN правила допускают merge при выполнении остальных ограничений.

### Requirement: Проверяемость настройки
The system MUST если текущих прав недостаточно, записать точные необходимые действия администратора и оставить acceptance незакрытым.

#### Scenario: Проверяемость настройки
- GIVEN отсутствует доступ к branch rules API
- WHEN изменение завершают
- THEN задачи настройки остаются открытыми и не маркируются выполненными.

## Cross-cutting Requirements

### Requirement: Snapshot isolation and explainability
The change MUST preserve repository-scoped immutable published UCM facts and return Evidence/Coverage/Resolution for inferred relations.

#### Scenario: Failure does not modify current publication
- GIVEN an existing published snapshot
- WHEN this feature encounters an invalid input or a storage error
- THEN the publication pointer and previously published facts remain unchanged
