# SQL execution sinks

## Проблема и цель

SQL discovery не доказывает выполнение. Нужны отдельные SQL_EXECUTE facts для
типизированных JDBC/Spring invocation sites и явная связь с construction origins.

## Границы

Opt-in execution adapter, local prepared handles, registry/entity contract,
normalized storage, publication gate и incremental reuse. SQL AST/effects,
parameter bindings, queue semantics, ORM и runtime reachability исключены.
