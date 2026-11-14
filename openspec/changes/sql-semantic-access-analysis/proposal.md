# SQL semantic access analysis

## Проблема и цель

Legacy SQL projection смешивает эффекты statements и теряет quoted case. Нужны
statement-local SQL AST facts, dialect profiles и typed accesses с unknown identity.

## Границы

SQL_STATEMENT/DATA_ACCESS, independent parsing, lexical source binding, DML/DDL
access effects, execution linking, normalized storage/readiness и incremental API.
Database identity/schema import, parameter/projection lineage и runtime effects
не входят в change. Legacy CLI не переключается.
