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
уходило на проверки внешних ключей при вставке связей — поиск по B-tree по
текстовым ключам. Локальный сервер работал с `shared_buffers` 128 МБ, так что
индексы такого snapshot в кэш не помещались. Набор из 400 файлов занял 2 ГБ
памяти процесса индексатора.

Сравнение строк заметно влияет на загрузку. Тот же набор из 400 файлов без
публикации на свежей базе:

| Locale базы | Всего, с | Из них вне Python, с |
| --- | --- | --- |
| `en_US.UTF-8` | 47 | ≈21 |
| `C` | 38 | ≈12 |

Идентификаторы UCM (`ucm:` + hex) и пути не нуждаются в языковой сортировке,
поэтому `COLLATE "C"` на ключевых колонках — кандидат на отдельный change. Здесь
схема не менялась. Эти эффекты — предмет дальнейшей работы по
`streaming-ucm-ingestion` и проверки на PostgreSQL 15/Linux; запросы поиска они не
затрагивают.

## PostgreSQL 15 verification protocol

`uv run python -m code_crawler.query_benchmark --groups 200 --output REPORT.json`
uses BENCHMARK_DATABASE_URL (a dedicated PostgreSQL 15 admin server with CREATEDB).
It creates/drops only its own uniquely named database and temporary Git fixture;
existing databases and production snapshots are not altered. The load is generated
Java/JDBC with five queries per repository, service calls and ambiguous type targets.
All facts pass normal indexing, source archival, validation and publication.

The harness records actual API SQL/arguments, warm wall-time samples and
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON), table cardinalities, index sizes and server
settings. It compares schema through 0017, then migration 0018, then current schema
(including lexical indexes). It measures committed batch-copy load separately from
parsing/validation, cleans its unpublished trial snapshots, and vacuums before plans.
It never forces seqscan off or silently substitutes a custom plan for production
plan_cache_mode=auto. Query outputs must remain identical across phases.

A run at ordinary scale does not close the >1M-single-snapshot acceptance item.
Full-snapshot validation remains memory intensive; scale and measured rows are
reported explicitly. Timing values are observations, not portable CI thresholds.

## PG15/Linux follow-up (2026-11-14)

The recorded workload uses `bfdb216` plus this change's benchmark harness (before
the entity-by-entity restoration in
`6afccac`), with 402 generated Java files and nonempty ambiguous-call candidates.
It runs on Linux x86_64 in a 2-CPU, 8-GiB workspace, using Docker `postgres:15`.
The original reader is retained in the three-phase baseline; its selective incoming
lookup is checked separately after the query fix. This isolates a query change
from the schema comparison. Historical macOS/PG18 figures above are a different
workload and machine and are not a speedup comparison. Code stays constant across
schema phases: before 0018 means current query shapes without its indexes, not
the historical queries before the SQL rewrites.

Committed batch-copy times exclude parsing, source archival, semantic validation
and publication. The benchmark deletes its trial snapshots and runs VACUUM ANALYZE
before each query phase; VACUUM does not compact physical index files. Short plan
and integration probes overlapped some copy trials, so load timings are operational
observations, not a controlled estimate of index-maintenance overhead.

The incoming reader originally filtered 74,403 unrelated relations to return one
CALLS relation. The fix selects target and candidate IDs through existing indexes
and then hydrates the bounded page; no migration is needed. The regression checks
3,000 unrelated relations, both resolved and partial candidate results, kind
filters, order and truncation under normal `plan_cache_mode=auto` after repeated
calls. It does not disable sequential scans or assert a machine-specific latency.

PG15 can still choose a hash join scanning 6,404 live symbols when hydrating
simple-name search results, a SQL-execution page or an outward graph trace. This remains recorded as a plan
limitation; the
unconditional no-sequential-scan requirement is not fully closed. A snapshot above
1M entities and memory-bounded validation also remain open.

### Recorded PG15 baseline

[Compact machine-readable results](benchmarks/query-pg15-2026-11-14.json) retain
counts, samples, result hashes, scan nodes, index sizes and the separate fixed-reader
plan. Full SQL/EXPLAIN reports are generated by the command above.

PostgreSQL 15.20, `en_US.utf8`, shared_buffers=128MB, work_mem=4MB,
plan_cache_mode=auto; two warmups and seven API samples per case. The published
snapshot contains 141,424 entities: 74,404 relations, 6,404 symbols, 402 source
files, 1,000 SQL statements and 1,000 executions. Initial indexing takes 84.29 s
(excluding validation/publication); the process peaks at 2,107.6 MiB RSS on the
older restoration code. This is not a measurement of the memory optimization
subsequently merged from origin/main.

SQL columns sum Execution Time from one EXPLAIN capture of each API's SELECTs;
wall time is the median of seven ordinary API calls and includes round trips and
hydration. BEGIN/COMMIT, planning and Python work are not included in SQL time.
The original typed incoming query is shown here; its fixed plan is separate.

| Query | SQL pre-0018, ms | SQL post-0018, ms | SQL current, ms | API current median, ms |
| --- | ---: | ---: | ---: | ---: |
| symbol_simple | 5.006 | 3.290 | 3.150 | 3.147 |
| symbol_signature | 1.204 | 0.155 | 0.198 | 0.914 |
| callers | 0.277 | 0.288 | 0.260 | 2.380 |
| callees | 0.727 | 0.653 | 0.760 | 2.506 |
| executions_owner | 0.356 | 0.276 | 0.271 | 3.054 |
| executions_page | 4.693 | 4.675 | 4.653 | 6.160 |
| table_readers | 1.131 | 0.301 | 0.244 | 2.251 |
| column_writers | 0.813 | 0.264 | 0.281 | 2.365 |
| trace_out | 4.019 | 4.192 | 4.144 | 6.149 |
| trace_in | 0.564 | 0.876 | 0.717 | 2.977 |
| evidence | 0.417 | 0.220 | 0.234 | 2.223 |
| typed_entity | 0.172 | 0.350 | 0.311 | 5.660 |
| typed_incoming | 25.424 | 28.116 | 27.224 | 33.280 |

Migration 0018 removes the measured execution-owner and SQL-access-name scans;
resolved caller lookup already used the target index with the current query shape.
The candidate index is exercised by the ambiguous-call workload and the fixed
reader probe. Symbol hydration scans remain as described above. The fixed reader
probe uses `ucm_relations_target_idx` and
`ucm_relation_candidates_candidate_idx`; its returned facts exactly match the
original reader. Probe timings overlapped a load trial and are not presented as a
controlled before/after latency comparison.

Fresh 0018 indexes, one published snapshot, before load-copy trials:

| Index | Bytes |
| --- | ---: |
| `ucm_entities_symbol_name_idx` | 81,920 |
| `ucm_relation_candidates_candidate_idx` | 16,384 |
| `ucm_sql_access_names_normalized_idx` | 90,112 |
| `ucm_sql_executions_owner_idx` | 131,072 |

| Schema | Committed copy 1, s | Committed copy 2, s | Median, s |
| --- | ---: | ---: | ---: |
| before_0018 | 34.86 | 36.29 | 35.58 |
| after_0018 | 36.91 | 35.99 | 36.45 |
| current | 33.23 | 33.61 | 33.42 |

The observed post-0018 median is about 2.5% higher; two samples do not establish a
statistically bounded overhead. The lower current-schema number does not prove
lexical indexes make ingestion faster. Cleanup between trials is excluded from
these figures and took much of the benchmark's elapsed time; this run did not
record a separate GC duration. The harness now reports GC duration explicitly for
future runs. Controlled ingest/GC measurements at larger scale remain necessary.


A01 requires current known migrations for operational GC. Historical benchmark
phases through 0017/0018 therefore remove only their own trial UUID in the isolated
benchmark database through the explicit UCM registry, under a transaction; no
foreign table discovery is used. Current-schema trials call normal snapshot GC.
The report labels this distinction in `cleanup_mode`; historical trial-cleanup
times are not measurements of the current operational GC preflight.
