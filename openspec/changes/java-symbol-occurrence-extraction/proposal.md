# Java symbol and occurrence extraction

## Проблема и цель

Legacy Java имена не различают перегрузки и не описывают lexical declarations/usages. Нужен adapter, заполняющий нормативные UCM Symbol/Scope/Occurrence с точными диапазонами, Evidence и честными неразрешёнными ссылками.

## Границы

Переиспользование существующего AST, syntax-level signatures, параметры/fields/locals, lexical references, canonical incremental callback. Без call applicability, classpath/import resolution, inheritance, SQL construction/execution и автоматического переключения legacy CLI. Явные исключения Java constructs отражены в PARTIAL Coverage.
