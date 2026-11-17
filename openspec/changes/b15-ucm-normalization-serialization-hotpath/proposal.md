# Proposal: Ускорение UCM normalization и сериализации spool

**Priority:** P1

## Why
incremental._spool_facts выполняет _inspect → recheck(FileAnalysis) → _rows → pickle.dump, а write-phase читает pickle.load; ingestion._stage дополнительно преобразует list[dict] в tuples для asyncpg.copy_records_to_table. Стоимость этих преобразований в процентах времени индексации не измерена отдельно.

## Intended outcome
Сокращение измеренного времени индексации без изменения канонических UCM-фактов, публикации, покрытия, разрешения и Evidence.

## Scope
- Профилировать отдельно strict validation/recheck, materialization UCM entities, mapping entity→normalized row, pickle encode/decode, dict→tuple и asyncpg COPY; считать байты и rows.
- Сократить повторные преобразования в течение одного доверенного pipeline: единый typed row schema/table column order и bounded iterator для spool и COPY вместо нескольких полных копий списков.
- Сохранить вызов всех проверок схемы и ссылочной целостности; если typed FileAnalysis уже прошёл проверку, допускается только формально доказанное устранение дублирования, с негативными тестами на изменённые поля.
- Сохранить приватный spool, его транзакционную изоляцию, отсутствие внешнего untrusted pickle interface и cleanup при cancel/crash.
- Сравнить CPU, RSS, spool_bytes, transfer rows, FK/check и canonical digest на 400/1000-file и mixed-language fixtures.

## Non-goals
- Не выключать recheck/validation ради ускорения без доказанной эквивалентности и защиты от мутаций.
- Не превращать pickle в публичный формат хранения/обмена или неподписанный файловый кэш.
- Не терять отсортированный/детерминированный порядок для UCM Evidence.

## Dependencies
B09; B03 already implemented; совместима с B05.

## Affected code
src/code_crawler/incremental.py; src/code_crawler/ingestion.py; src/code_crawler/ucm.py; src/code_crawler/performance_baseline.py; tests/integration/test_incremental_indexing.py; tests/test_ingestion.py

## Acceptance
- CPU profiler отражает снижение proven overhead на row-heavy fixture; end-to-end выигрывает либо остаётся в пределах допустимого noise при сохранении semantics.
- Отдельный benchmark на conversion/spool без PostgreSQL и полный PG15 тест.
