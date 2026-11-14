# Proposal: Обязательный PG15 CI для main

## Why
Hosted CI на 18ebcf7 успешен, однако обязательность статуса PostgreSQL 15 в правилах main не подтверждена.

## Goal
Сделать невозможным merge изменений при неуспешном либо отсутствующем обязательном CI check.

## Scope
- Зафиксировать стабильное check name PostgreSQL 15 и имя workflow CI.
- Описать создание branch ruleset/branch protection для main с required status check и запретом bypass по умолчанию.
- Проверить правило через контролируемый тестовый PR (не мержить).
- Если текущих прав недостаточно, записать точные необходимые действия администратора и оставить acceptance незакрытым.
- Не включать paths filters, создающие недоступный required check для части PR.

## Non-goals
Не переписывать тестовый pipeline, если он уже зелёный; не обходить разрешения GitHub.

## Dependencies
Уже существующий .github/workflows/ci.yml

## Impacted code
.github/workflows/ci.yml; docs/ci.md; openspec/; GitHub repository rules (внешняя настройка)

## Priority
P1 организационный

## Acceptance summary
1. Required check.
2. Missing status.
3. Реальный success.
4. Проверяемость настройки.
