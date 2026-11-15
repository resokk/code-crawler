# Атомарная публикация UCM

`validate_snapshot(conn, snapshot_id)` сначала короткой транзакцией переводит
BUILDING в VALIDATING, блокируя дальнейшую запись фактов. Затем порциями читает
нормализованные таблицы, восстанавливает сущности и проверяет модели, полноту
subtypes, ordered rows, Evidence/Coverage, ссылки и инварианты `UcmBatch` вне
длинной блокировки repository (см. «Память при validation»). При успехе короткая транзакция сохраняет validation receipt
и переводит snapshot в READY. Ошибка оставляет его VALIDATING без receipt;
некорректный индекс не публикуется. Повтор validation допустим; READY возвращает
прежний count. Пустой batch допустим как индекс пустого репозитория.

`publish_snapshot(conn, repository_id, snapshot_id, *, expected_snapshot_id)`
требует READY с receipt. expected_snapshot_id — текущий pointer, либо None для
первой публикации. Короткая транзакция блокирует строку repository, проверяет
ожидаемый pointer, переводит прежний PUBLISHED в RETIRED, новый READY в PUBLISHED
и переключает pointer. При несовпадении ожидания возвращается ValueError.
Читатель одним запросом published_snapshot видит целиком старую или новую версию.
Канонические факты при публикации не копируются и не удаляются. В этой же
транзакции строится repository-local [discovery generation](global-discovery-catalog.md).
Ошибка проекции откатывает и publication pointer. Проекция линейна по symbols/DB/BPMN
facts нового snapshot; блокировка repository теперь включает эту работу. Остальные
repositories не блокируются и не переиндексируются. Refresh старых публикаций
выполняется отдельной CLI-командой; чтение явно сообщает отсутствие поколения.

`rollback_publication` имеет те же аргументы и возвращает ранее RETIRED snapshot
с receipt. Это единственный дополнительный lifecycle переход RETIRED→PUBLISHED;
обратный переход не разрешает менять immutable факты. SQL deferred constraints
требуют соответствия pointer и единственного PUBLISHED snapshot при commit.
READY/PUBLISHED требуют validation receipt. Receipt неизменяем; ошибки и отмена
publication transaction сохраняют прежние pointer и состояния целиком.

API требуют соединение без внешней transaction. Валидация полная, но держит в
памяти только порцию snapshot; публикация короткая, не повторяет анализ графа. При обрыве
процесса до receipt snapshot остаётся VALIDATING и может пройти validation снова.
При потере ответа после commit вызывающий код перечитывает pointer перед новым
CAS-запросом. Для согласованного чтения фактов нескольких запросов клиент должен
использовать `reader.published_reader` (read-only REPEATABLE READ), закрепляющий
выбранную publication на весь compound read. Контракт: [canonical-read.md](canonical-read.md).

Migration 0005 добавляет receipts, lifecycle guard и deferred pointer constraints;
старые migration-файлы не меняются. Legacy writer/CLI продолжают работать.
Проверяются структурные факты, а не истинность анализа, границы исходных bytes
или полнота capabilities. Контроль DDL/прямого SQL владельца БД не входит в gate;
производственные записи должны идти через ingestion/validation/publication API.

## Память при validation

`load_snapshot_batch` восстанавливает сущности по одной: строки таблиц и документ
освобождаются по мере превращения в модели, общий JSON на весь snapshot не
строится. На время восстановления одинаковые мелкие значения (Position,
SourceRange, EntityRef, Resolution, Coverage) разделяются через пул
`ucm.shared_values`: модели заморожены, поэтому общий экземпляр безопасен. Вне
восстановления пул выключен.

Замер на snapshot из 124 тыс. сущностей:

| | Объектов моделей | Память восстановления | Пик index + validation |
| --- | --- | --- | --- |
| исходно | 936 тыс. | — | 1855 МБ |
| без общего JSON | 936 тыс. | +845 МБ | 922 МБ |
| с общими значениями и порционной индексацией | 336 тыс. | +573 МБ | 639 МБ |

`load_snapshot_batch` остаётся для потребителей, которым нужен весь batch (поисковые
проекции, benchmark), и по-прежнему держит все модели: около 4,6 КБ на сущность.

### Проверка порциями

Change `streaming-ucm-ingestion`. `validate_snapshot` больше не восстанавливает
snapshot целиком. Правила `UcmBatch` вынесены в функции `ingestion.check_entities`,
`check_unique_reports`, `check_semantics` и `check_scope_cycles`; `UcmBatch`
вызывает их же, поэтому решения совпадают.

- Сущности читаются порциями по 2 000 в порядке `entity_id`; каждая проходит
  строгий JSON и `check_entities`.
- Сущности, на которые порция ссылается, дочитываются одним запросом и лежат в
  кэше не больше 20 000 моделей (при переполнении кэш очищается). Цепочки
  «операция → значения» и «scope → родители → владелец» дочитываются сразу.
- Уникальность путей файлов и единственность producer у Value проверяются
  множествами строк, которые живут всю проверку: это идентификаторы, не модели.
- Строка вспомогательной таблицы без владельца нужного вида не попадает ни в одну
  порцию; итоговая сверка числа прочитанных строк с числом строк snapshot отвергает
  её как `unconsumed canonical rows`.
- Отчёты SourceAnalysis и циклы scopes проверяются по парам идентификаторов.
- Межсущностные SQL-правила (`check_semantics`) получают все SQL-факты snapshot:
  constructions, statements, accesses, placeholders, bindings, database accesses и
  связи USES_SQL_CONSTRUCTION, EXECUTES_STATEMENT, BINDS_PARAMETER,
  USES_DATABASE_CONTEXT.

Ограничение: память растёт с числом SQL-фактов и с числом файлов и значений
(строки), но не с числом сущностей. Чтобы убрать и это, SQL-правила нужно
переписать на запросы — change `b02-bounded-memory-snapshot-validation`.

Замер на PostgreSQL 15.20, snapshot из 141 424 сущностей (macOS arm64):

| | Время, с | Пик RSS процесса, МиБ |
| --- | ---: | ---: |
| восстановление целиком (`load_snapshot_batch`) | 4,8 | 688 |
| проверка порциями | 17,8 | 170 |

Проверка стала медленнее: ссылки каждой порции читаются из базы, а не из словаря
в памяти.
