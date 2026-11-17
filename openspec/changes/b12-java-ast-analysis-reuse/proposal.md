# Proposal: Повторное использование Java AST и промежуточного анализа

**Priority:** P1 при подтверждении профилем

## Why
JavaSemanticAnalyzer.analysis и другие подклассы вызывают super().analysis, а HTTP/Java binding catalogs выполняют дополнительные обходы. Наличие AST/cache внутри Java catalog не доказывает отсутствие повторной работы между passes; сначала нужен tracer B09 для конкретных вызовов parse/extractor и IR.

## Goal
Сократить время индексации при неизменной семантике UCM, Evidence, Coverage, Certainty и опубликованных snapshots.

## Changes
- Инструментировать числа Tree-sitter parse calls, symbol extraction и traversal passes отдельно для prepare, Java full analysis, HTTP/Kafka/BPMN enrichment.
- Там, где профилем подтверждена повторная работа, передавать immutable per-file parse/symbol scope lookup внутри одного worker/analysis invocation без долгоживущего кеширования Node по repository.
- Кэшировать только результаты с зависимостями source_sha256, catalog fingerprint, analyzer profile и версией parser, не включая конфиденциальные сырые исходники в shared cache.
- Обеспечить clear-on-file/end-of-slice и после отмены; сохранить exact SourceRange/Evidence/AST diagnostic behavior.
- Сравнить parser CPU, file memory и semantic digest до/после на Java + ORM, duplicated FQN и malformed fixtures.

## Non-goals
- Не изменять грамматику Java, SQL semantics или правила parser fallback.
- Не заставлять Python worker делить Tree-sitter Node объекты между процессами.
- Не добавлять долговременный глобальный AST-cache без threat model и измерений.

## Dependencies
B09, совместимо с B10; предшествует B14.

## Code surface
src/code_crawler/java_adapter.py; src/code_crawler/java_symbols.py; src/code_crawler/java_calls.py; src/code_crawler/java_semantic.py; src/code_crawler/java_database.py; src/code_crawler/java_orm.py; tests/test_java_symbols.py; tests/test_java_calls.py

## Acceptance evidence
- Экономия parse/traversal CPU подтверждена B09 on/off fixtures; если повторов нет — закрыть диагностикой без усложнения архитектуры.
