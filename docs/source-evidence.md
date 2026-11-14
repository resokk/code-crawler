# Reproducible source evidence

Новые UCM snapshots могут стать READY/PUBLISHED только с полным архивом SourceFile
bytes. Политика — STORE_CAPTURED_BYTES для clean и dirty working tree. Git HEAD,
branch, dirty flag и source fingerprint остаются provenance; HEAD не заменяет
идентичность фактически захваченных bytes. Источник анализа — snapshot + inventory
fingerprint + per-file SHA-256. Untracked files/symlinks по-прежнему вне inventory.

Миграция 0017 добавляет immutable content-addressed blobs (repository + SHA-256),
snapshot/file → blob links с origin CAPTURED_WORKTREE или PROVIDED_BYTES и совместимость
для snapshots, уже PUBLISHED/RETIRED на момент миграции. Старые published snapshots
не изменяются; их rollback разрешён, но отсутствие bytes имеет явный статус
UNAVAILABLE_LEGACY. Новые snapshots без bytes не получают такого исключения.
Migration сериализуется с изменениями lifecycle, чтобы конкурентная публикация
не потеряла совместимость. Snapshot в BUILDING может получить bytes перед
validation; старый READY/VALIDATING без архива требует повторной индексации.
Повторный запуск migration не создаёт новых исключений (migration runner once-only).

Incremental indexing и legacy migration архивируют **те самые captured bytes** в
одной транзакции с UCM facts/manifests, не перечитывая checkout для архива.
No-change reuse повторно использует blob по hash, snapshot links создаются заново.
Идентичность Git и snapshot SourceFile SHA проверяются независимо. Archive failure
откатывает facts/links, pointer остаётся прежним. Пустой snapshot без SourceFiles
не требует фиктивного blob. Адаптеры не получают зависимости от PostgreSQL.

Generic producers после ingest_batch вызывают source_evidence.archive_sources с
SourceInput и origin PROVIDED_BYTES **до** validate_snapshot. Bytes/metadata/hash
должны соответствовать сохранённым SourceFiles. Позднее attach к READY запрещено.
Validation проверяет полноту архива до замораживания; SQL publication guard также
не допускает обхода через прямое изменение state. Blobs immutable сразу, links замораживаются вместе с facts с VALIDATING;
их нельзя переписать или truncate после замораживания. Существующий snapshot GC
может удалить links/exemption только для RETIRED под code_crawler.gc; PUBLISHED
не удаляется. Blobs пока сохраняются даже после удаления snapshots; освобождение
неиспользуемых blobs — отдельная политика. Восстановление гарантировано пока
snapshot сохраняется, а не после его явного удаления retention-командой.

`read_source_fragment(conn, repository_id, snapshot_id, SourceRange)` читает только
PUBLISHED/RETIRED snapshot указанного repository, возвращает raw bytes и provenance
(path, file SHA, commit, fingerprint, dirty, origin). Она не читает filesystem и
повторно проверяет SHA-256 полного файла до slicing. SourceRange: line 1-based,
UTF-8 byte columns 0-based, exclusive end; multibyte boundaries и выход за bytes
отклоняются. Binary bytes хранятся без decode; SourceRange требует валидный UTF-8
на границах выбранных строк. Empty/CRLF/EOF ranges сохраняют точные bytes.
Unknown source, repository mismatch, unpublished snapshot, legacy unavailable,
invalid coordinates и hash mismatch — явные ошибки, без fallback к mutable checkout.

CLI snapshot reports показывают source_evidence status и число archived/source files,
a также commit/fingerprint/dirty. Source bytes retrieval API не публикует секреты
в логи и пока не является MCP-инструментом. Access control — следующий production
change; существующая модель доступа PostgreSQL сохраняется.
