# Proposal: Безопасный кэш SQLGlot разбора одинаковых запросов

**Priority:** P1 при высоком duplicate ratio

## Why
JavaSemanticAnalyzer.semantic_constructions разбирает SQL constructions через SQLGlot. Многие SQL/JPQL конструкции могут повторяться в разных файлах и методах, но ratio уникальных запросов и время парсинга не измерены. Повторная SQLGlot parse работа — гипотеза, требующая профильного подтверждения.

## Goal
Сократить время индексации при неизменной семантике UCM, Evidence, Coverage, Certainty и опубликованных snapshots.

## Changes
- Подсчитать total SQL parse attempts, distinct exact texts, parse errors и CPU SQLGlot отдельно по dialect/version/parse options; не записывать SQL text или его raw hash в общий monitoring.
- При подтверждённых дублях реализовать bounded invocation-local LRU для результата разбора или нормализованного immutable summary; ключ учитывает SQL text bytes, dialect, SQLGlot version и parser options.
- Не шарить mutable sqlglot.Expression AST между построителями, которые модифицируют узлы; возвращать безопасную копию либо immutable model только при доказанной эквивалентности.
- Отдельно кэшировать non-success parse diagnostics без сокрытия SourceRange/варианта/парсинг-статуса; подтверждать partial variants без DataAccess.
- Зафиксировать cache hit/miss/size/eviction и сравнить synthetic duplicate-heavy и mostly-unique SQL fixtures.

## Non-goals
- Не соединять разные placeholder positions или запросы, отличающиеся регистрами quoted identifiers, whitespace или dialect.
- Не использовать общий кэш между tenants/repositories и не сохранять raw SQL как глобальный fingerprint.
- Не менять обнаруженные SQL executions и certainty.

## Dependencies
B09; Java semantic existing; A06 security.

## Code surface
src/code_crawler/java_semantic.py; src/code_crawler/sql_semantic.py; src/code_crawler/jpql.py; tests/test_sql_semantics.py; tests/test_java_semantic.py; docs/sql-semantics.md

## Acceptance evidence
- При высокой повторяемости — измеренное снижение SQL parse CPU; на уникальных запросах overhead ограничен и результат идентичен.
