# Capability: unchanged-published-snapshot-fastpath

## ADDED Requirements

### Requirement: Полная эквивалентность
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Полная эквивалентность
- **GIVEN** Повторный запуск имеет те же commit, source bytes и adapter/profile fingerprints
- **WHEN** включён opt-in reuse-unchanged-publication
- **THEN** команда возвращает ID текущего published snapshot без полной clone/validate, никакие факты/публикация не изменены

### Requirement: Source changed
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Source changed
- **GIVEN** Файл изменился после предыдущей индексации
- **WHEN** вызывают fast-path
- **THEN** новый snapshot создаётся и проходит обычный pipeline

### Requirement: Commit changed
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Commit changed
- **GIVEN** Commit SHA изменился при одинаковом содержимом
- **WHEN** вызывают fast-path
- **THEN** сохраняется корректная provenance policy; прежний published snapshot не выдаётся как доказательство нового commit

### Requirement: Version changed
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Version changed
- **GIVEN** Изменился dialect, catalog fingerprint или Java SQL max_paths
- **WHEN** планируется fast-path
- **THEN** ускорение отклонено, затронутые анализы пересчитываются

### Requirement: CAS race
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: CAS race
- **GIVEN** Другой процесс опубликовал snapshot во время проверки
- **WHEN** fast-path завершает
- **THEN** нет устаревшего snapshot ID, результат перепроверяется или переход к обычному пути

### Requirement: No-op audit
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: No-op audit
- **GIVEN** Запуск ничего не изменил
- **WHEN** формируется job/CLI result
- **THEN** статус REUSED_CURRENT явно отличим от CREATED/PUBLISHED и не скрывает отсутствие нового snapshot

### Requirement: Performance claims require reproducible evidence
The change MUST NOT be called an improvement merely because one sample ran faster. Use fixed fixtures and record environment, algorithmic workload and full regression checks.

#### Scenario: Speed optimization changes semantics
- **GIVEN** a baseline UCM snapshot with exact canonical digest and Evidence
- **WHEN** an optimized mode produces an incompatible graph or invalid readiness receipt
- **THEN** acceptance fails even if wall time decreases
