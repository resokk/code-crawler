# UCM operation/value model

## Проблема и цель

Контракт деклараций не описывает передачу значений между выражениями и вызовами. Вводим Operation, Value и минимальный data flow для будущего восстановления SQL и parameter lineage.

## Границы

Типизированный контракт и валидатор отдельных документов, JSON Schema и тесты. Без исполнения кода, изменения Java extraction, SQL sinks, хранения и полного CFG/SSA. Общий Relation/Evidence контракт вводится следующим change.
