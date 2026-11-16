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

`--copies N` sets the number of committed copy + GC trials per schema phase
(default 2); `--copies 0` skips them and never loads the whole snapshot into
memory, which is how the run above 1M entities is made. The report also records
indexing and validation time and the process peak RSS before any copy trial.
Timing values are observations, not portable CI thresholds.

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

On the 2026-11-14 run PG15 chose a hash join scanning 6,404 live symbols when
hydrating simple-name search results, a SQL-execution page or an outward graph
trace. That limitation is closed by the 2026-11-15 follow-up below.

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

## PG15 follow-up (2026-11-15): symbol hydration, controlled load and GC

### Symbol hydration

The remaining scans came from three joins to `ucm_symbols`: the simple-name search
itself, `_entities` (endpoints of every relation page) and the owner lookup of SQL
executions. The table holds a few thousand rows per snapshot, so for a page of ~50
keys PostgreSQL 15 preferred a hash join over reading the whole table. Each join is
now a `LATERAL` subquery ending in `OFFSET 0`: the planner cannot flatten it, so
every key is looked up through `ucm_symbols_pkey`. Results are unchanged; no index
or migration is added. `test_symbol_hydration_does_not_scan_all_symbols` reproduces
the old plan on 3,000 symbols under normal `plan_cache_mode=auto` and fails without
the rewrite. It does not disable sequential scans.

### Controlled run at 141,424 entities

[Compact results](benchmarks/query-pg15-2026-11-15-141k.json). PostgreSQL 15.20
(Homebrew), macOS arm64 (Apple M4, 16 GiB), `en_US.UTF-8`, shared_buffers=128MB,
work_mem=4MB, plan_cache_mode=auto; code at `7deedc1` plus this change. The server
ran nothing else and the machine was kept awake; three committed copies and three
GC runs per schema phase (`--copies 3`), seven API samples per query.

After 0018 and on the current schema no structural query scans `ucm_entities`,
`ucm_symbols`, `ucm_relations`, `ucm_sql_executions`, `ucm_data_accesses` or
`ucm_sql_access_names` sequentially. Before 0018 the expected scans of
`ucm_sql_executions` and `ucm_sql_access_names` remain. Query results are identical
across the three phases.

| Query | SQL pre-0018, ms | SQL post-0018, ms | SQL current, ms | API current median, ms |
| --- | ---: | ---: | ---: | ---: |
| symbol_simple | 2.52 | 2.09 | 2.09 | 2.44 |
| symbol_signature | 0.47 | 0.07 | 0.06 | 0.40 |
| callers | 0.13 | 0.10 | 0.10 | 0.92 |
| callees | 0.40 | 0.40 | 0.40 | 1.18 |
| executions_owner | 0.17 | 0.13 | 0.13 | 1.36 |
| executions_page | 3.71 | 3.71 | 3.69 | 4.79 |
| table_readers | 0.55 | 0.17 | 0.17 | 1.32 |
| column_writers | 0.53 | 0.16 | 0.16 | 1.32 |
| trace_out | 2.98 | 3.06 | 3.02 | 4.14 |
| trace_in | 0.32 | 0.34 | 0.35 | 1.00 |
| evidence | 0.09 | 0.09 | 0.09 | 0.74 |
| typed_entity | 0.07 | 0.08 | 0.09 | 1.87 |
| typed_incoming | 0.14 | 0.11 | 0.12 | 1.37 |

These are a different machine from the 2026-11-14 Linux run; compare phases within
one table, not tables with each other.

| Schema | Committed copy, s (3 runs) | Median, s | GC of the copy, s (3 runs) | Median, s |
| --- | --- | ---: | --- | ---: |
| before_0018 | 23.25, 25.36, 25.60 | 25.36 | 124.61, 125.91, 126.60 | 125.91 |
| after_0018 | 24.57, 25.00, 24.74 | 24.74 | 120.34, 122.77, 122.75 | 122.75 |
| current | 25.69, 25.01, 24.75 | 25.01 | 120.88, 122.89, 124.04 | 122.89 |

Bounded ingest cost: the medians differ by at most 0.62 s (2.5%) while samples
within one phase spread by up to 2.35 s, and the phase with the 0018 indexes is not
the slowest. The four indexes add no measurable load cost at this scale. Indexing
the sources took 41.97 s and sliced validation 20.41 s; the process peaked at
416 MiB RSS before the whole batch was loaded for the copy trials.

GC is five times slower than loading the same snapshot and does not depend on the
0018 indexes. See [ingest-jobs.md](ingest-jobs.md#время-gc) for the cause.

### Snapshot above 1M entities

[Compact results](benchmarks/query-pg15-2026-11-15-1m.json). Same server, settings
and code; `--groups 1500 --copies 0`: 3,002 generated Java files, one published
snapshot of 1,060,524 entities (558,004 relations, 207,004 occurrences, 48,004
symbols, 7,500 SQL statements and executions). Copy trials are skipped at this
size because of GC time, so no whole batch is loaded into memory.

After 0018 and on the current schema no structural query scans a large UCM table
sequentially; results are identical across phases.

| Query | SQL pre-0018, ms | SQL post-0018, ms | SQL current, ms | API current median, ms |
| --- | ---: | ---: | ---: | ---: |
| symbol_simple | 15.05 | 10.28 | 10.24 | 10.31 |
| symbol_signature | 3.71 | 0.07 | 0.07 | 0.33 |
| callers | 0.37 | 0.12 | 0.12 | 0.71 |
| callees | 0.39 | 0.39 | 0.38 | 0.98 |
| executions_owner | 0.43 | 0.15 | 0.14 | 1.61 |
| executions_page | 5.41 | 5.26 | 5.25 | 6.23 |
| table_readers | 2.89 | 0.21 | 0.20 | 0.98 |
| column_writers | 2.87 | 0.19 | 0.19 | 0.92 |
| trace_out | 4.65 | 4.63 | 4.68 | 5.60 |
| trace_in | 0.30 | 0.29 | 0.31 | 0.98 |
| evidence | 0.11 | 0.10 | 0.10 | 0.64 |
| typed_entity | 0.09 | 0.08 | 0.09 | 1.79 |
| typed_incoming | 0.34 | 0.13 | 0.14 | 1.41 |

Against the 141k snapshot only `symbol_simple` grows noticeably: the name `load`
matches 1,500 symbols, all of which are read and sorted before the page is cut.
The other queries stay within about 1.5 ms of SQL time for 7.5 times the data.

| Index (0018), one published snapshot | Bytes |
| --- | ---: |
| `ucm_entities_symbol_name_idx` | 483,328 |
| `ucm_relation_candidates_candidate_idx` | 65,536 |
| `ucm_sql_access_names_normalized_idx` | 573,440 |
| `ucm_sql_executions_owner_idx` | 876,544 |

Pipeline: indexing 405.4 s, sliced validation 213.2 s, process peak 1,012 MiB RSS.
Load cost and GC were not measured at this size; the 141k figures above stand for
them.

## B04: bulk-load FK optimization

`uv run python -m code_crawler.bulk_benchmark --pairs 500000 --repeats 2 \
  --locale en_US.utf8 --budget-seconds 900 --output REPORT.json`

`BENCHMARK_DATABASE_URL` должен указывать на выделенный PostgreSQL 15 admin server
с CREATEDB. Harness создаёт только собственную `crawler_bulk_<uuid>` базу из
`template0` и удаляет её в finally, включая ошибки. Поддержаны locale `C` и
`en_US.utf8`; locale выбирается только для новой базы, существующие БД не меняются.
Никакие FK/индексы не отключаются. Для baseline harness можно запустить с кодом
`08d9708` (до B04); API `ingest_stream` не меняется.

Fixture из `pairs` методов и столько же CALLS, плюс один SourceFile, даёт
`2*pairs+1` entities. Каждый call содержит Evidence и PARTIAL Coverage, ссылается
на следующий метод, включая ссылки в следующие порции и замыкание цепи.
Это синтетические typed UCM facts, а не замер Java parser: единственный archived
source явно помечен как synthetic evidence. Разбор исходников не входит в результат.

Отчёт отдельно содержит wall duration клиентских COPY, INSERT SELECT, ANALYZE и
SET CONSTRAINTS (с round trips), число SQL-команд, staging high-water bytes,
полное время committed ingest, archive, semantic validation и publication.
`total_seconds` включает генерацию/recheck моделей, commit и diagnostics, но не
создание БД/миграции и последующие reader probes. Обычный published reader проверяет
точное восстановление sample Symbol/Relation; validation проверяет все entities.
Повторы сохраняют предыдущие published/retired snapshots в той же базе.
Размеры всех индексов и SHA256 `ingestion.py` сохраняются в отчёте.

Бюджет по умолчанию — 900 с на trial; CLI возвращает ненулевой код после записи
отчёта при превышении. Это порог данного opt-in benchmark, не переносимый latency
assert для CI и не принудительный timeout долгого запроса. Планы equality FK probe
сохраняются до/после ANALYZE при production `plan_cache_mode=auto`; EXPLAIN probe
не утверждает, что видит внутренний SPI plan PostgreSQL RI trigger.

Initial isolated PG15 smoke (20 001 entities, C locale): prior code COPY 0.265 s,
INSERT SELECT 2.598 s, FK checks 47.623 s (88 SET commands), total 76.887 s.
A single ALL check alone: FK 45.138 s, total 70.178 s. Adding ANALYZE before the
check: FK 0.592 s, total 11.241 s. These single samples motivated the change;
they do not establish a portable speedup factor. No index or collation migration
is introduced; added-index write/storage overhead is zero. Forward migration of
all historical ID keys would add table/index rewrites without fixing stale stats.
Linguistic SQL identifier semantics and quoted/case-sensitive names stay unchanged.

### Controlled B04 measurements

The controlled runs use Linux x86_64 with a 2-CPU cgroup quota and 8 GiB memory,
Docker `postgres:15`, shared_buffers=128MB, work_mem=4MB,
plan_cache_mode=auto, fsync=on and synchronous_commit=on. PGDATA is a dedicated
5-GiB tmpfs, max_wal_size=128MB, min_wal_size=32MB, checkpoint_timeout=60s.
The original disk-backed million-entity attempt was cancelled before commit when
workspace free space became low; its partial timings are excluded. tmpfs timings
are not a throughput claim for production disks. Each trial runs alone; no test
suite or second benchmark overlaps it. The initial smoke figures above used the
original disk-backed setup and are listed only to explain the investigation.

On both C and en_US.utf8, baseline first-load FK EXPLAIN selects
`ucm_entities_symbol_name_idx` by snapshot and filters entity_id over the symbol
set. After ANALYZE the same probe uses the unique entity-ID index. A repeat on the
old code already benefits from populated-table statistics: this is why first and
repeat trials must be compared separately. New ANALYZE work has a cost on warm
loads; no universal ingestion speedup is claimed. No extra index is introduced.

| 20 001 entities | First ingest, s | First FK, s | First full cycle, s | Repeat full cycle, s | Peak fact staging, MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline C | 51.177 | 44.951 | 70.378 | 11.069 | 14.10 |
| B04 C | 5.941 | 0.730 | 10.906 | 9.277 | 7.08 |
| baseline en_US.utf8 | 50.206 | 44.429 | 70.329 | 10.620 | 14.10 |
| B04 en_US.utf8 | 6.865 | 0.688 | 10.849 | 12.794 | 7.08 |

Two trials per setup are observations, not confidence intervals. ANALYZE client
wall time at this scale is 0.25–0.92 s per trial. The warm en_US trial demonstrates
that the optimization's added work is not free. `chunk_size=5000` pairs means
10 000 entities per fact-staging slice in these measurements; the writer's maximum
slice is 20 000 entities. The million-entity run uses the same chunk size, so its
peak staging should remain proportional to a slice rather than the snapshot.

The million-entity acceptance repeats use separate fresh databases because keeping
two full snapshots plus discovery generations exceeded the available tmpfs quota.
The first invocation completed its first trial and reader checks; the following
trial was cancelled before storage exhaustion. Its completed timing log is
retained explicitly as a log-only observation (unrecorded metrics are not filled
in). The next acceptance trial uses `--repeats 1` in a new disposable database.
Previous-snapshot preservation is separately checked by the two-trial 20k runs and
the integration suite. No global tmpfs mount was changed.

For such constrained environments run the command twice with `--repeats 1` and
distinct output files. CLI now atomically saves each verified completed trial to
`--output`; `complete=false` and `requested_trials` distinguish an incomplete
multi-trial run. A subsequent failure or cancellation preserves that checkpoint
while database cleanup still runs. Report serialization is outside trial timing.

Benchmark provenance: the measurements above start from `08d9708` and schema
through 0029, with B04 changing only the writer/benchmark. During verification,
main advanced to A03 (`d53ea67`), adding migration 0030's index on
`ucm_database_objects`. The synthetic fixture has no DATABASE_OBJECT rows and
A03 does not change ingestion.py or incremental.py; the measured writer SHA256
is unchanged. Final full-suite and CI validation run with A03/0030 included.

### Million-entity acceptance

[Machine-readable observations, phases, settings, plans and index sizes](benchmarks/bulk-pg15-2026-11-16.json).
Both fresh trials load 1 000 001 entities and pass full semantic validation,
publication and exact sample read-back with unchanged INFERRED/PARTIAL proof.

| Trial | Committed ingest, s | FK flush, s | Validation, s | Publication, s | Full cycle, s | Budget 900 s |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| first completed trial (log) | 427.134 | 55.976 | 234.197 | 101.071 | 762.416 | passed |
| fresh repeat (JSON checkpoint) | 401.075 | 54.051 | 228.094 | 89.994 | 719.186 | passed |

The fresh repeat's fact-staging high-water is 7 512 064 bytes (7.16 MiB), against
7 421 952 bytes (7.08 MiB) at 20k on the same 10k-entity slices. Larger method
numbers slightly widen each row; staging does not grow with the number of slices.
Client process peak RSS for the fresh repeat is 138.64 MiB, including validation;
this is not PostgreSQL server memory. One published database occupies 2 737 356 135
bytes, which explains why retaining two such snapshots plus WAL did not fit the
5-GiB fixture tmpfs. The first completed trial predates JSON checkpoint support;
its unrecorded staging/index metrics are deliberately omitted rather than inferred.

No 1M baseline trial of the old code was run; there is no claimed controlled
before/after speedup at 1M. The comparison is the
recorded 20k fresh/warm matrix, the deterministic bad-plan regression, and two
successful bounded 1M acceptance repetitions. These measurements cover synthetic
bulk ingestion, not parsing or production-disk throughput.

## Current end-to-end baseline

[B01 baseline protocol](performance-baseline.md) measures current-schema capture,
analysis, staging/FK, validation/publication, readers and GC independently, with
repeated 400-file runs, a 1,000-file run and a >1M-entity attempt. This complements
the historical index comparisons above.
