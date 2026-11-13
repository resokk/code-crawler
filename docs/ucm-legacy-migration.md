# Управляемая миграция legacy индекса

Команды `migrate-index <legacy-name> --repository-key <key>`,
`compare-index <key>`, `use-index <key> --backend legacy|ucm`, `show-index <key>`
вводят compatibility bridge без удаления repos/nodes/edges/data_*.
`index` сохраняет прежнее поведение; после обновления legacy индекса миграцию
можно повторить, получив новый immutable snapshot.

Миграция читает legacy Graph и проверяет его эквивалентность повторному анализу
captured tracked bytes через существующие Java/PLPlus анализаторы. Ошибки parser,
несовпадение graph/commit или изменение worktree отклоняют операцию. Snapshot
получает актуальный fingerprint/dirty/branch. Repository UUID связывается с
legacy id явно через repository_key; имя/basename не становится UCM identity.

Envelope-конвертер сохраняет file/class/method/function/sql_query: функции пока
представлены METHOD. Logical key compatibility сущности включает kind, path,
qualified_name и ordinal; это временная identity, не сигнатура перегрузки.
SQL_QUERY становится SQL_CANDIDATE, не SQL execution. Допустимые contains edges
с реальным file evidence становятся INFERRED Relations с PARTIAL Coverage.
Остальные legacy edges/attrs/data_refs сохраняются в отдельной compatibility
проекции ingest_legacy_nodes/edges/refs по snapshot — не в произвольном canonical
JSONB. Projection сохраняет полный legacy ответ, включая text SQL, data accesses,
PLPlus attrs и прежние ошибки executes; это не новые подтверждённые UCM факты.

Проекция и canonical batch записываются одной транзакцией, затем проходят UCM
gate и отдельную CAS publication. Legacy остаётся неизменным при ошибке UCM.
Read backend изначально legacy. `compare-index` сравнивает полный Graph projection
и commit с legacy, возвращает mismatch и ограничения semantic bridge.
`use-index --backend ucm` требует успешного сравнения и фиксирует backend в БД;
`--backend legacy` позволяет вернуться без удаления snapshots. `show-index` и
публичный read_graph каждый раз читают выбранный backend из БД. UCM reader
читает только опубликованный snapshot; multi-query чтение выполняется в
REPEATABLE READ transaction. Обычная переиндексация legacy не меняет UCM pointer.

Это переходный read path с совместимым Graph ответом, а не законченная семантика
Java/SQL или GraphRAG. MCP пока каркас; его будущие tools должны использовать
выбранный read path либо нормативный UCM query engine. Новые adapters заменят
compatibility projection нормативными facts. Инкрементальный API остаётся доступен,
но bridge делает полный разбор: shared PLPlus entities ещё не имеют нормативного
file ownership. Legacy tables не выводятся из эксплуатации на этом этапе.
