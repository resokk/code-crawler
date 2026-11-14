# Индексы под запросы UCM

Change `ucm-query-index-optimization` плана [2.0](development-plan-v2.md).
Типовые запросы — это запросы [структурного поиска](structural-search.md); все они
ограничены одним `snapshot_id`.

## Что измерялось

Набор: синтетический Java-репозиторий, 400 файлов (200 JDBC-репозиториев по 5
запросов, 200 сервисов с цепочкой вызовов), профиль `orm`. Один snapshot:
124 185 сущностей, 64 838 связей, 6 206 символов, 8 005 имён SQL-доступов.
`EXPLAIN (ANALYZE, BUFFERS)` на прогретом кэше после `ANALYZE`.

Замеры сделаны на локальном PostgreSQL 18 (macOS), а не на целевом PostgreSQL 15:
абсолютные цифры — ориентир, планы нужно подтвердить на PG15.

## Baseline и результат

Время — сумма всех SQL-запросов одной функции поиска.

| Запрос | До, мс | После, мс | Что было |
| --- | --- | --- | --- |
| search_symbols, простое имя | 47.5 | 2.4 | Seq Scan по `ucm_entities` и `ucm_symbols` |
| search_symbols, полное имя и сигнатура | 46.2 | 0.06 | то же: `OR` по двум таблицам мешал индексу |
| find_callers | 10.2 | 0.10 | Seq Scan по `ucm_relations` из-за `OR EXISTS` по candidates |
| find_callees | 0.21 | 0.17 | индекс уже был |
| find_sql_executions по символу | 0.93 | 0.13 | Seq Scan по `ucm_sql_executions` |
| find_sql_executions, все (50) | 5.6 | 4.0 | индексы были; время уходит на Evidence 50 связей |
| find_table_readers | 3.0 | 0.32 | Seq Scan по `ucm_sql_access_names` |
| find_table_writers с колонкой | 0.93 | 0.16 | то же |
| trace_dependency out, глубина 4 | 1.5 | 1.3 | индексы были |
| trace_dependency in, глубина 4 | 0.10 | 0.10 | индексы были |
| get_evidence | 0.07 | 0.07 | первичные ключи |

После изменений полных сканов больших таблиц нет. Seq Scan остаётся только по
`ucm_source_files` (строка на файл) и пустой `ucm_relation_candidates` — там он
дешевле индекса.

## Индексы (миграция 0018)

| Индекс | Под что | Размер на наборе |
| --- | --- | --- |
| `ucm_entities_symbol_name_idx (snapshot_id, name) WHERE entity_type='SYMBOL'` | поиск символа по простому имени | 256 kB |
| `ucm_relation_candidates_candidate_idx (snapshot_id, candidate_id)` | callers через неоднозначные связи | 8 kB (кандидатов нет) |
| `ucm_sql_executions_owner_idx (snapshot_id, owner_symbol_id)` | SQL executions метода | 424 kB |
| `ucm_sql_access_names_normalized_idx (snapshot_id, part, normalized)` | читатели/писатели по нормализованному имени таблицы, колонки, схемы | 240 kB |

Размеры — после загрузки трёх одинаковых snapshots (372 836 сущностей всего).
Три запроса переписаны, чтобы индексы применялись: `OR` по двум таблицам заменён на
`UNION ALL` идентификаторов, `EXISTS` по имени таблицы — на `JOIN`.

Индексы по `relation_kind` и `access_kind` отдельно не добавлены: существующие
`ucm_relations(snapshot_id, source_id|target_id, relation_kind)` уже покрывают
запросы по виду связи, а `access_kind` фильтруется после поиска по имени и сам
малоселективен. GIN не понадобился: все условия — равенство. Индекс по
`ucm_database_objects` появится вместе с запросом, который читает разрешённые
объекты БД.

## Цена при загрузке

Полная индексация того же набора: 49 с с новыми индексами против 53 с до них
(во втором замере была ещё validation и публикация) — в пределах шума. B-tree
индексы строятся при вставке; отдельной фазы нет.

## Замечание о масштабе загрузки

Набор из 3000 файлов (≈930 тыс. сущностей) за 50 минут не загрузился: время
уходило на проверки внешних ключей при вставке связей — поиск по B-tree с
дорогим сравнением строк в locale collation. Набор из 400 файлов занял 2 ГБ
памяти процесса индексатора. Оба эффекта — предмет change `streaming-ucm-ingestion`
и отдельной проверки на PostgreSQL 15/Linux; запросы поиска они не затрагивают.
