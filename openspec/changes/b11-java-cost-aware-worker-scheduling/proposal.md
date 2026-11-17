# Proposal: Адаптивное распределение Java-файлов по процессам

**Priority:** P1

## Why
java_parallel.JavaProcessPool.analyze() делит очередные 64 исходника на равные contiguous groups. Один тяжёлый SQL-метод может занять дольше всей группы; на маленьких и catalog-heavy fixtures multiprocessing медленнее. Опция --analysis-workers N уже есть и default=1; задача не должна дублировать её.

## Goal
Сократить время индексации при неизменной семантике UCM, Evidence, Coverage, Certainty и опубликованных snapshots.

## Changes
- Определить дешёвый, безопасный cost estimate для файла (размер, количество methods, SQL candidates/paths по текущему parser catalog) без повторного полного SQL анализа.
- Добавить deterministic weighted scheduling при N>1: ограничение задач/bytes in-flight, фиксированный canonical output order независимо от completion order, no prefetch будущих snapshot slices.
- Не выбирать автоматически больше CPU, чем разрешает явная настройка, cgroup CPU/memory budget; для малых workloads выполнить в parent sequential path без создания subprocess pool (opt-in adaptive).
- Добавить метрики per-worker busy/idle/wall, queue skew, startup overhead и fallback; параметры стратегии не включать в analysis fingerprint, пока normalized facts не меняются.
- Сравнить balanced/imbalanced CPU-heavy и catalog-heavy fixtures при workers=1/2/4, с синтетическим тяжёлым и лёгкими файлами.

## Non-goals
- Не выполнять speculative анализ одного файла в нескольких worker.
- Не менять количество или certainty UCM relations по завершённости задач.
- Не создавать скрытого безлимитного executor/prefetch.

## Dependencies
B09; независимо от B10, но измерить оба сочетания.

## Code surface
src/code_crawler/java_parallel.py; src/code_crawler/java_adapter.py; src/code_crawler/cli.py; src/code_crawler/parallel_benchmark.py; tests/test_java_parallel.py; docs/parallel-snapshot-preparation.md

## Acceptance evidence
- Положительное или нейтральное изменение времени относительно contiguous split на фиксированных трёх fixtures; не принимать ускорение за счёт отключения анализа.
- Не повышать default workers автоматически без доказанного выигрыша.
