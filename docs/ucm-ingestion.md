# UCM bulk ingestion

`code_crawler.ingestion.UcmBatch` — полный замкнутый batch одного репозитория:
repository_id UUID, entities tuple всех SourceFile/CodeEntity/Symbol/Scope/
Occurrence/Operation/Value/Relation/ExternalReference/SqlConstruction/SqlExecute/SqlStatement/DataAccess/SqlBinding/SqlPlaceholder/DatabaseContext/DatabaseObject/DatabaseAccess/OrmMapping/OrmQuery/OrmOperation/SourceAnalysis. repository_id каждого
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
ответственностью адаптера. Writer держит в памяти один экземпляр batch: повторная
JSON-валидация идёт по одной сущности и сверяет результат с оригиналом, не создавая
копию batch, а нормализованные records готовятся и уходят в COPY порциями по
20 000 сущностей. Ошибка в любой порции откатывает всю загрузку. Streaming анализа,
resume, durable ingest jobs/stages/diagnostics и partial-file batches потребуют
отдельного расширения. Ошибки возвращаются вызывающей стороне; автоматического
retry или публикации нет. Readiness gate описан в
[ucm-publication.md](ucm-publication.md).

Инкрементальный orchestrator формирует новый полный batch из переиспользованных
и вновь извлечённых facts и сохраняет его вместе с file manifests одной
транзакцией. См. [ucm-incremental.md](ucm-incremental.md). Public ingest_batch
сохраняет прежний контракт полного закрытого batch.

SQL semantic validation дополнительно проверяет уникальную statement position,
candidate text slice, partial construction isolation, access/statement/effect
consistency и EXECUTES_STATEMENT origin через execution construction resolution.
Identifier parts и statement reasons загружаются отдельными ordered/typed rows.

Lineage validation проверяет token slice/ordinal, selector shape, binding owner
и Value, setter CALL/API и JDBC inputs, BINDS_PARAMETER membership/selector,
PARAMETER_COLUMN ownership/object kind и запрет definite links у incomplete binding.
Binding reasons загружаются/восстанавливаются отдельными ordered rows.

Database identity validation проверяет global object key/name shape, file-owned
projection identity, context search_path, execution/statement/context membership и
resolved target kind/database/version/fingerprint. SQL FK дополнительно требует
существующего immutable imported object и READY version; импорт inventory выполняется
отдельным API, не внутри UcmBatch или code indexing.

ORM validation проверяет entity/attribute symbol kinds и class ownership,
status/reasons, CALL/API/callable scope, invocation/effect consistency, named
query matching и captured query. ORM database targets обязаны принадлежать
context database/version/fingerprint. ORM annotations/recovered queries не
подменяются JSONB payload; names/flags/reasons сохраняются typed rows.

SourceAnalysis reports создаёт orchestrator registry. Batch проверяет source-file
reference и максимум один report на файл; nested capabilities/diagnostics проверяют
strict UCM validators. Reports/capability reasons/diagnostic ranges загружаются
нормализованно и восстанавливаются readiness gate без сессионного состояния.

## Потоковая загрузка

Change `streaming-ucm-ingestion`. `ingest_stream(conn, snapshot_id, repository_id,
chunks)` принимает асинхронный поток порций сущностей и загружает их в пустой
BUILDING snapshot; `ingest_batch` не заменён и работает как раньше. В памяти
держится только текущая порция. Порции идут в любом порядке и могут ссылаться на
сущности следующих порций: всё копируется в staging, а ссылки проверяют отложенные
FK после переноса. Загрузка — одна транзакция: сбой источника, висячая ссылка,
дубликат ID, чужой repository_id или отмена оставляют snapshot пустым, повтор в
тот же snapshot возможен.

Межсущностные семантические правила `UcmBatch` при потоковой загрузке не
проверяются; их проверяет `validate_snapshot` до READY, поэтому невалидный
snapshot опубликовать нельзя. Сама validation по-прежнему читает snapshot целиком,
а `index_incremental` пока использует batch loader.

### Куда уходит память индексации

Замер на 400 Java-файлах (348 КБ исходников, 124 тыс. сущностей, профиль `orm`),
RSS процесса:

| Шаг | RSS, МБ |
| --- | --- |
| после импортов и чтения исходников | 67 |
| после `prepare` (каталог Java) | 346 |
| после анализа всех файлов | 583 |
| пик индексации | 653 |
| пик с validation | 922 (до оптимизации чтения — 1855) |

Каталог Java при `prepare` извлекает факты символов всех файлов и хранит их до
конца запуска: 191 МБ pydantic-объектов, около 0,7 МБ на файл. Анализ файлов
порциями память не возвращает: анализаторы кэшируют результаты по файлам
(рост ≈0,57 МБ на файл и при освобождении результатов). Поэтому переключение
`index_incremental` на `ingest_stream` сейчас ничего не экономит — оно отложено до
переделки каталога Java, чтобы тот хранил только нужное для разрешения имён.
Память растёт линейно: около 1,6 МБ на файл на пике индексации.


Этот замер предшествует `50a71ca` (occurrences вычисляются по запросу) и `be53229`
(ORM base cache ограничен 16 файлами). Он описывает прежнее удержание фактов;
память после этих изменений нужно измерить повторно перед выбором следующего
шага streaming pipeline. PG15 query benchmark из [query-indexes.md](query-indexes.md)
тоже использует прежний `bfdb216` и не измеряет эффект этих оптимизаций.
