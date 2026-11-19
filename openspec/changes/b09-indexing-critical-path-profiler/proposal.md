# Proposal: Профилирование критического пути индексации

**Priority:** P0 — сначала измерения

## Why
B01 показывает на 400 Java-файлах 37.30 с analyze, 15.76 с transfer, 10.76 с FK и 43.13 с validation, но nested профили не отделяют построение Java catalog, SQL/ORM, повторный обход AST, Pydantic/row conversion, pickle spool, IPC и временные DB операции. После новых Java/COW/parallel изменений прежние цифры уже не отражают текущий SHA.

## Goal
Сократить время индексации при неизменной семантике UCM, Evidence, Coverage, Certainty и опубликованных snapshots.

## Changes
- Добавить малозатратные фазовые метрики capture, Java catalog build, parse, calls, SQL recovery, SQLGlot, ORM, DTO enrichment, UCM normalization, spool serialize/deserialize, staging, transfer, deferred FK, readiness и publication. Вложенные интервалы помечать: их нельзя суммировать.
- Показывать CPU wall/user/system, Python allocations/peak RSS, bytes/entities/rows, child-process CPU/peak memory, IPC bytes/worker startup; не читать исходный текст и не сохранять SQL или секреты в профиле.
- Добавить режим детального профилирования с выключенным по умолчанию трейсингом; baseline без профилирования измерять отдельно из-за накладных расходов.
- Сформировать воспроизводимые входы: small, Java SQL path-heavy, catalog-heavy, SQL-dense, 400/1000-file PG15; фиксировать commit SHA и зависимости.
- Сохранять machine-readable breakdown/critical path, суммарное время end-to-end и неучтённый остаток; при неполном выполнении явно помечать absent/stopped stage.

## Non-goals
- Не переписывать анализаторы, не пытаться оптимизировать по статистике одного прогона.
- Не включать high-cardinality метки методов/символов в обычный monitoring, не логировать приватный код.

## Dependencies
Существующий --profile, observability и B01 performance_baseline; независима от B05–B08.

## Code surface
src/code_crawler/profiling.py; src/code_crawler/performance_baseline.py; src/code_crawler/java_adapter.py; src/code_crawler/incremental.py; src/code_crawler/ingestion.py; docs/performance-baseline.md; tests/test_profiling.py

## Acceptance evidence
- Два или более независимых профиля (один Java-heavy, один PG-heavy), одинаковые факты с profiling on/off.
- Измеренная overhead профилирования и отсутствие секретов.
- Документированный top-5 bottlenecks и regression fixture для B10–B17.
