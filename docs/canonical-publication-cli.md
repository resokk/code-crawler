# Canonical publication CLI

`index-sources` по умолчанию создаёт BUILDING snapshot. `--publish` завершает
тот же запуск: index → validate_snapshot → publish_snapshot. Используется
`IncrementalResult.base_snapshot_id` как expected pointer; конкурентная публикация
не перезаписывается. Validation замораживает BUILDING в VALIDATING и переводит
валидный snapshot в READY, публикация — в PUBLISHED атомарно с pointer.

```sh
uv run code-crawler index-sources /repo --repository-key org/repo --publish
uv run code-crawler snapshot validate SNAPSHOT_UUID
uv run code-crawler snapshot publish SNAPSHOT_UUID --expected-current none
# Если индекс уже опубликован:
uv run code-crawler snapshot publish NEW_UUID --expected-current CURRENT_UUID
```

`--expected-current` обязателен: `none` означает отсутствие pointer, UUID —
точно ожидаемую published версию. Publish сам вызывает validation; отдельная
validate-команда позволяет подготовить READY без публикации. Повторная публикация
текущего PUBLISHED snapshot с expected-current равным ему идемпотентна.
RETIRED snapshot не переиздаётся этой командой: rollback — отдельная операция API.

Вывод: snapshot_id, repository_id, status, entity_count, current published ID и
число SourceAnalysis diagnostics по severity. Ошибки выводятся CLI и дают exit 1;
старый pointer сохраняется при invalid facts, unknown snapshot и CAS conflict.
Каждый запуск `index-sources` записывает задание; повтор и очистка — в
[ingest-jobs.md](ingest-jobs.md).
Неудачная validation может оставить VALIDATING для диагностики; READY после
CAS conflict сохраняется для явного retry с новым expected-current.

Используются существующие validation/publication API и storage; новых миграций
нет в change 01. Source reproducibility теперь обеспечена migration 0017 и
архивом exact captured bytes для новых snapshots; validation/publication требуют
полноту архива. Старые published snapshots имеют явный UNAVAILABLE_LEGACY.
См. [source-evidence.md](source-evidence.md). Snapshot reports включают archive
status/counts, commit/fingerprint/dirty. Read API, default backend и CI enforcement
остаются отдельными changes [плана 2.0](development-plan-v2.md).
