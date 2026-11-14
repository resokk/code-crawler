# Design: Обязательный PG15 CI для main

## Context and current implementation
Hosted CI на 18ebcf7 успешен, однако обязательность статуса PostgreSQL 15 в правилах main не подтверждена.

## Proposed solution
### Decision 1
Зафиксировать стабильное check name PostgreSQL 15 и имя workflow CI.

### Decision 2
Описать создание branch ruleset/branch protection для main с required status check и запретом bypass по умолчанию.

### Decision 3
Проверить правило через контролируемый тестовый PR (не мержить).

### Decision 4
Если текущих прав недостаточно, записать точные необходимые действия администратора и оставить acceptance незакрытым.

### Decision 5
Не включать paths filters, создающие недоступный required check для части PR.

## Integration and compatibility
- Reuse canonical UCM entities, immutable published snapshots and existing migration/adapter contracts.
- Keep existing public APIs compatible unless this change explicitly requires a versioned extension.
- Do not resolve cross-repository links during ingestion; expose deferred candidates only at query time.
- Every inferred relationship must retain Resolution, Coverage and Evidence; do not promote UNKNOWN to STATIC_PROVEN.

## Alternatives and trade-offs
- Avoid a broad rewrite or introducing a parallel storage model; targeted updates are easier to verify and roll back.
- If an optimization weakens referential integrity or snapshot immutability, reject it and preserve the current behavior.

## Failure modes and recovery
- Fail closed for invalid input, unknown ownership or missing permissions; report diagnostics without leaking source bytes.
- Database modifications require migration, backward-compatibility review and integration tests on PostgreSQL 15.
- A failed operation MUST leave the previously published snapshot readable and unchanged.

## Implementation surfaces
.github/workflows/ci.yml; docs/ci.md; openspec/; GitHub repository rules (внешняя настройка)

## Dependencies
Уже существующий .github/workflows/ci.yml
