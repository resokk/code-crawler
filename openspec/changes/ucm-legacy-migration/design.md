# Решение

Migration 0007 связывает stable UCM repository UUID с legacy repo ID и хранит read_backend. ingest_legacy_nodes/edges/refs сохраняют исходный Graph в нормализованных строках по snapshot, включая typed node/edge/ref columns и существующие attrs JSONB. Это compatibility projection, не canonical UCM blob. Header ingest_legacy_snapshots хранит counts, чтобы отличать пустой граф от отсутствующего/неполного projection. Все projection tables используют snapshot immutable guards.

migrate-index читает legacy graph в REPEATABLE READ, затем secure capture tracked bytes. Public indexer.build_sources переиспользует существующие Java/PLPlus analyzers без повторного IO; результат должен точно совпасть с сохранённым graph и commit. После сборки проверяется повторный fingerprint/HEAD/dirty/branch. Ошибка прерывает переход, legacy данные не меняются.

Converter создаёт SourceFile и envelope CLASS/METHOD/SQL_CANDIDATE; PLPlus function пока METHOD. Compatibility keys включают ordinal, поэтому overload signature identity пока не заявляется. Только допустимые contains с реальным file-level Evidence становятся INFERRED/PARTIAL Relations. Legacy executes/calls/data accesses сохраняются в projection, но не превращаются в новые подтверждённые semantic facts. Ограничения возвращаются compare report.

Canonical COPY и projection фиксируются одной транзакцией. Далее применяется прежний validation gate и CAS publication с pointer, прочитанным до анализа. Default read backend не переключается автоматически. Повтор миграции создаёт новый snapshot. После DB failure может остаться пустой BUILDING metadata row; прежние pointer/facts/legacy строки сохранены.

compare-index сравнивает весь Graph и commit с опубликованным projection, показывает counts и ограничения, возвращает exit 1 при mismatch. use-index ucm блокирует repository publication row, проверяет comparison и меняет persistent backend только при совпадении. use-index legacy восстанавливает чтение legacy без удаления history. read_graph/show-index читают выбранный backend одним REPEATABLE READ readonly transaction; состояние не хранится в процессе. UCM path читает только published pointer и проверяет matching projection header/counts.

После очередного legacy index UCM читатель продолжает видеть прежний published snapshot до повторного migrate-index; это явно управляемый переход. Новый publish без compatibility projection приводит к явной ошибке reader, а не к тихому fallback. MCP сейчас каркас и не получает новых инструментов: будущий интерфейс будет использовать read path/query engine.

Индексирование shared PLPlus entities пока не имеет нормативного file ownership, поэтому bridge не притворяется incremental adapter. Совместимый Graph сохраняет известные legacy ошибки executes; новая SQL достоверность будет реализована changes 14–22. Legacy tables/data import не выводятся из эксплуатации.
