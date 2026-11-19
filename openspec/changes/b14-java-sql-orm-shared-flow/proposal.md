# Proposal: Совместное переиспользование проходов SQL и ORM по Java-методам

**Priority:** P2 — после стабилизации B12/B13

## Why
В JavaSqlAnalyzer, JavaExecutionAnalyzer и JavaOrmAnalyzer есть собственные обходы методов/flow, включая _recover(... JpaFlow ...) для ORM. Несмотря на COW, один и тот же Java method может обрабатываться в несколько заходов. Разделять можно лишь read-only промежуточные факты, а не сливать разные семантики SQL и JPA.

## Goal
Сократить время индексации при неизменной семантике UCM, Evidence, Coverage, Certainty и опубликованных snapshots.

## Changes
- Добавить per-method tracer числа _recover visits, state clones, SQL/ORM dispatches и CPU; выбрать один подтверждённый hotspot method-heavy fixture.
- Выделить immutable shared inputs (method AST boundary, symbol/scope lookup, constant env, resolved API classification) из анализа SQL и JPA без объединения mutable state machines.
- Пересчитать downstream SQL construction/execution/ORM только из проверенного intermediate summary; сохранить SQL path budget (default 256) и отдельные parser statuses.
- Проверить одинаковые normalized UCM entities, certainty, unresolved candidates, path overflow report и determinism full/incremental.
- Включить feature flag для сравнения и быстрого rollback; не делать оптимизацию, если профили не дают выигрыша.

## Non-goals
- Не сливать SQL execution и ORM query creation как один вид события.
- Не заменять path-sensitive analysis эвристическим text matching.
- Не повышать partial statements до confirmed.

## Dependencies
B09; желательно B12, B13; existing Java SQL COW и budget.

## Code surface
src/code_crawler/java_sql.py; src/code_crawler/java_execution.py; src/code_crawler/java_orm.py; src/code_crawler/jpa_flow.py; src/code_crawler/java_adapter.py; tests/test_java_sql_cow.py; tests/test_java_orm.py

## Acceptance evidence
- Снижение CPU подтверждено без дополнительного значимого роста RSS; при неуспехе задача закрывается исследованием, не усложняя pipeline.
