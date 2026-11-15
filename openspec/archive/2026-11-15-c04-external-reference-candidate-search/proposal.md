# Proposal: Разрешение кандидатов ExternalReference по запросу

## Why
ExternalReference хранит selector, hints и Evidence локально, но глобального query-time сопоставления с доказательствами пока нет.

## Outcome
Разрешение кандидатов ExternalReference по запросу. Нормализовать selector-specific lookup (Symbol signature, DB identity, HTTP method/path/service, Kafka/BPMN IDs). Фильтровать кандидатов выбранным resolver_context и compatibility constraints, с bounded fanout. Возвращать RESOLVED только при единственной доказанной совместимой цели; иначе AMBIGUOUS/PARTIAL/UNRESOLVED с reasons. Каждый кандидат связывать с его snapshot, source Evidence, rule и certainty; unknown framework semantics не повышать.

## Scope
- Нормализовать selector-specific lookup (Symbol signature, DB identity, HTTP method/path/service, Kafka/BPMN IDs).
- Фильтровать кандидатов выбранным resolver_context и compatibility constraints, с bounded fanout.
- Возвращать RESOLVED только при единственной доказанной совместимой цели; иначе AMBIGUOUS/PARTIAL/UNRESOLVED с reasons.
- Каждый кандидат связывать с его snapshot, source Evidence, rule и certainty; unknown framework semantics не повышать.

## Non-goals
Не строить cross-repo canonical Relations и не считать совпадение имени доказательством вызова.

## Dependencies
C02,C03

## Impacted code
src/code_crawler/ucm.py; src/code_crawler/search.py; src/code_crawler/migrations/; tests/integration/; docs/

## Priority
P1
