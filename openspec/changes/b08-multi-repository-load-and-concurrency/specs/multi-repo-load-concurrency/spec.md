# Capability: multi-repo-load-concurrency

## ADDED Requirements

### Requirement: Независимая публикация
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Независимая публикация
- GIVEN индексируется repo A
- WHEN repo B обновляется
- THEN публикация A не блокируется глобальным reindex.

### Requirement: Независимые имена
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Независимые имена
- GIVEN два репозитория имеют одинаковый FQN/table
- WHEN поиск scoped
- THEN UCM entities не смешиваются.

### Requirement: Чтение при записи
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Чтение при записи
- GIVEN опубликован snapshot A
- WHEN строится следующий snapshot
- THEN поисковые запросы продолжают читать A.

### Requirement: Сбой одного job
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Сбой одного job
- GIVEN DB error в одном repo
- WHEN другие jobs продолжаются
- THEN их публикации не откатываются.

### Requirement: Snapshot integrity
The system MUST preserve published snapshot immutability, deterministic evidence and transparent partial coverage.

#### Scenario: Failure during feature execution
- GIVEN a previously published repository snapshot
- WHEN this change encounters an invalid fact, cancellation or PostgreSQL error
- THEN the published snapshot stays readable and no false RESOLVED facts are introduced
