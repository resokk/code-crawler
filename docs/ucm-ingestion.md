# UCM bulk ingestion

`code_crawler.ingestion.UcmBatch` — полный замкнутый batch одного репозитория:
repository_id UUID, entities tuple всех SourceFile/CodeEntity/Symbol/Scope/
Occurrence/Operation/Value/Relation/ExternalReference. repository_id каждого
entity должен равняться str(UUID). Порядок entities не важен. Дубликаты ID,
отсутствующие или неверно типизированные ссылки, циклы parent_scope и несколько
producer одного Value отклоняются до записи. Внешние зависимости ссылаются
только на локальный ExternalReference, внешние индексы не требуются.

`ingest_batch(conn, snapshot_id, batch)` требует свободное соединение без внешней
транзакции и пустой BUILDING snapshot того же репозитория. Это загрузка полного
snapshot, не append/upsert API; для повтора после успешной загрузки нужен новый
snapshot. Для пустого batch допустим пустой snapshot. Writer не меняет state или
publication pointer и не переключает legacy CLI.

Подготовка и повторная валидация моделей выполняются в worker thread. Writer
берёт FOR UPDATE lock snapshot, сериализуя загрузки и переходы state. Нормализованные
records загружаются COPY в session-local temporary staging tables ON COMMIT DROP.
Pass 1 переносит envelope rows ucm_entities; pass 2 — subtype, refs, ordered
arguments/candidates, evidence и coverage reasons. FK проверяются до commit.
Все канонические записи и staging находятся в одной транзакции: любая ошибка
или cancellation откатывает загрузку; temp tables удаляются. Новый snapshot
после ошибки остаётся пустым BUILDING, прежний опубликованный индекс неизменен.

Канонический storage не использует числовой surrogate ID. Возвращаемый mapping
logical entity ID → (snapshot UUID, entity ID) задаёт физический составной ключ.
Межсущностные ссылки сохраняют logical ID и дополняются тем же snapshot_id.
Temporary staging не хранит JSON-документы: COPY использует типизированные колонки.
Для Value literal null записывается JSON null, для nonliteral — SQL NULL.
Selectors, hints, signature, TypeRefs, unresolved statuses и partial сохраняются.

SQL ограничения дополняют Python validation. До загрузки проверяются все модели,
локальные источники/типы, Evidence файлы, scope refs, TypeRef targets, операции и
их Value refs. Границы range относительно bytes не проверяются (batch содержит
hash, но не исходные bytes). Полнота анализа и истинность Evidence остаются
ответственностью адаптера. Writer держит весь batch/records в памяти: streaming,
resume, durable ingest jobs/stages/diagnostics и partial-file batches потребуют
отдельного расширения. Ошибки возвращаются вызывающей стороне; автоматического
retry или публикации нет. Readiness gate будет следующим change.
