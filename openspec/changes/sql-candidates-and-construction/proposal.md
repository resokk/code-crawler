# SQL candidates and construction

## Проблема и цель

Legacy SQL discovery смешивает найденную строку с execution и теряет структуру
неизвестных частей. Нужны проверяемые construction/variant/fragment facts.

## Границы

Opt-in Java SQL adapter поверх call graph; lexical constants, bounded branch
recovery, typed UCM, normalized storage, immutable publication и incremental reuse.
Execution sinks, SQL semantic AST, bindings и lineage остаются отдельными changes.
