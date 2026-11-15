# D07 completion receipt

Completed: 2026-11-15 (Europe/Moscow).

Implementation: [`f840ad9`](https://github.com/resokk/code-crawler/commit/f840ad936379ca9b2c44fe75d47f8e9fa106e642).
[CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43707790495)
succeeded: **1171 passed in 148.18s**, including migration of a clean database,
lint, formatting, unit/integration/regression tests and clean-working-tree checks.
Local full suite after integrating current GC and slice-validation work:
**1171 passed in 219.09s**.

Acceptance: tests/test_kafka_adapter.py and
tests/integration/test_kafka_storage.py; mixed-language compatibility fixture in
tests/integration/test_vbscript_adapter.py mirrors the active CLI wrapper while
retaining no-reanalysis assertions. Focused Kafka suite: 28 passed;
Kafka/VBScript compatibility suite: 29 passed.

Verified: Spring listener/KafkaTemplate, Apache producer/consumer/NewTopic syntax,
cluster separation, DTO/serde local/missing/ambiguous/generic cases, dynamic and
invalid topics, safe bounded constants/configuration, source Evidence, shared AST
and BPMN catalog reuse, full/incremental equality, config edit/version invalidation,
consumer removal, repository isolation and failed-producer publication preservation.

The dedicated adapter wraps the canonical Java profile, preserves profile keys,
shares parsed ASTs and forwards catalog exports. Migration 0027 extends existing
UCM symbols/relations; there is no separate graph or adapter-owned SQL/network I/O.
All runtime wiring, delivery and deployment conclusions remain unproved. Kafka
capability is PARTIAL; configuration is a source candidate. Dynamic topics and
external resources preserve explicit uncertainty. Global Kafka discovery/resolver
integration remains deferred; qualified local lookup is verified.

Full supported APIs, parser/config budgets and limitations:
docs/kafka-message-intelligence.md. The normative proposal, design, specification
and completed tasks are preserved in this directory.
