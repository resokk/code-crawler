# Proposal: Снижение повторного построения Java-каталога в subprocess

**Priority:** P1

## Why
В java_parallel._worker_main каждый spawn-процесс вызывает _build_analyzer(config.sources), повторно строя каталог всего репозитория. В catalog-heavy benchmark 32 файла: 1 worker — 6.14 с/214 МиБ суммарного RSS, 2 workers — 8.81 с/539 МиБ, 4 — 12.22 с/717 МиБ. Запуск 1 worker должен остаться baseline.

## Goal
Сократить время индексации при неизменной семантике UCM, Evidence, Coverage, Certainty и опубликованных snapshots.

## Changes
- Добавить измеряемый сериализуемый компактный catalog snapshot из immutable declaration/symbol/signature/owner/URI lookup, исключив AST Node/Tree, DB connection, callbacks и Pydantic facts вне нужного профиля.
- Пересылать/подключать каталог к worker один раз при запуске, без повторного полного построения в каждом процессе; безопасно допускать минимальный локальный parse AST для обрабатываемого файла, если он нужен анализатору.
- Выбрать transport после замера (memory mapped read-only data или bounded serialized blob/pipe). Зафиксировать версию layout, hashes входных source bytes и fingerprint анализа; malformed/old version отклонять.
- Соблюдать owner и lifecycle ресурсов: worker termination/cancel/process crash не оставляет временные файлы, пароли или file descriptors, и не меняет published UCM.
- Сравнить startup, total wall/CPU и сумму RSS parent+children для 1/2/4 workers на catalog-heavy и SQL-heavy fixtures.

## Non-goals
- Не передавать Tree-sitter Node/Pydantic graph как потенциально небезопасный shared mutable object.
- Не менять разрешение Java symbols, import/type/overload semantics или Java analysis_version без необходимости.
- Не использовать глобальный межрепозиторный кэш со смешанными границами доступа.

## Dependencies
B09; использует существующие JavaProcessPool и JavaSourceAdapter.

## Code surface
src/code_crawler/java_parallel.py; src/code_crawler/java_adapter.py; src/code_crawler/java_catalog.py; tests/test_java_parallel.py; tests/integration/test_parallel_preparation.py; docs/parallel-snapshot-preparation.md

## Acceptance evidence
- Либо измеренное уменьшение catalog-heavy startup+RSS без изменения digest, либо явный отказ от новой схемы с зафиксированными данными.
- Сохранён корректный путь для workers=1 и source parse failures.
- Никакого external pickle/file API.
