# База данных и миграции

Подключение — `asyncpg`, строка подключения берётся из переменной окружения `DATABASE_URL`:

```bash
export DATABASE_URL=postgresql://user:password@host:5432/dbname
```

## Миграции

Схема меняется только миграциями. Миграция — SQL-файл в `src/code_crawler/migrations/`, имя задаёт порядок:

```
0001_nodes_and_edges.sql
0002_embeddings.sql
```

- Файлы применяются в порядке сортировки имён; номер — с ведущими нулями.
- Применённую миграцию не редактировать и не переименовывать — любое изменение схемы идёт новым файлом.
- Каждая миграция выполняется в одной транзакции, поэтому в ней нельзя использовать команды, запрещённые внутри транзакции (например, `CREATE INDEX CONCURRENTLY`).
- Применённые миграции записываются в таблицу `schema_migrations` (`name`, `applied_at`). Её создаёт `db init`.

## `code-crawler db init`

Разворачивает схему на пустой БД: создаёт таблицу `schema_migrations` и сразу применяет все миграции — с тем же прогрессом и теми же правилами, что `db migrate`. Повторный запуск безопасен: на инициализированной БД он применяет только недостающие миграции.

## `code-crawler db status`

Сравнивает миграции в коде с применёнными в БД. Ничего не меняет.

| Состояние | Статус | Код выхода |
| --- | --- | --- |
| все миграции применены | `✓ Состояние БД` | 0 |
| `db init` ещё не выполнялся | `✗ Состояние БД: БД не инициализирована, выполните …` | 1 |
| есть не применённые | `✗ Состояние БД: схема устарела, не применено: …` | 1 |
| в БД есть миграции, которых нет в коде | `✗ Состояние БД: БД новее кода, неизвестные миграции: …` | 1 |

## `code-crawler db migrate`

Применяет недостающие миграции по порядку, показывая прогресс и имя каждой применённой.

- Если миграция падает, она откатывается целиком; ранее применённые остаются, команда завершается с кодом 1 и именем упавшей миграции.
- Если БД не инициализирована или новее кода, команда ничего не применяет и завершается с кодом 1.
- Одновременный запуск двух миграций безопасен: вторая ждёт первую (advisory-блокировка) и применяет только то, что осталось.

## Интеграционные тесты PostgreSQL 15

Тесты `tests/integration/` используют настоящую БД. Для локального запуска:

```bash
docker run --rm -d --name code-crawler-test-pg15 \
  -e POSTGRES_PASSWORD=integration -p 127.0.0.1:55432:5432 postgres:15
# Дождаться готовности: docker exec code-crawler-test-pg15 pg_isready -U postgres
TEST_DATABASE_URL=postgresql://postgres:integration@127.0.0.1:55432/postgres \
  uv run pytest -m integration
# После проверки:
docker stop code-crawler-test-pg15
```

`TEST_DATABASE_URL` должен указывать на отдельный тестовый сервер PostgreSQL 15;
пользователю требуется CREATEDB. Каждый тест создаёт уникальную временную БД и
удаляет только её после завершения. Проверяются миграции, откат ошибочного DDL,
COPY графа и откат загрузки, каскадное удаление связей и реальные процессы CLI.
Расширения пока не требуются: текущие миграции их не используют.

Локально без `TEST_DATABASE_URL` интеграционные тесты явно пропускаются. В CI
и с `--require-postgres` отсутствие URL, выбор без integration tests и их skip
делают проверку ошибочной: [ci.md](ci.md). Ошибки доступа и
несовместимая версия при заданном URL приводят к падению тестов. Обычный набор
можно запустить через `uv run pytest -m 'not integration'`.

## UCM snapshots

Миграция `0003_ucm_repository_snapshots.sql` добавляет независимые таблицы
репозиториев, snapshots и publication pointer в `public`. Legacy-данные
сохраняются. Контракт metadata, ограничения и границы текущего API описаны в
[snapshots.md](snapshots.md). Атомарная публикация описана в [ucm-publication.md](ucm-publication.md).

Миграция `0004_ucm_core_storage.sql` добавляет канонические таблицы UCM,
snapshot-scoped FK и защиту immutable content. Структура и границы SQL validation
описаны в [ucm-storage.md](ucm-storage.md). Bulk writer вводится следующим change.

Миграция `0005_ucm_atomic_publication.sql` добавляет immutable validation receipts,
проверку lifecycle и согласованности publication pointer при commit.
Валидация, CAS-публикация и восстановление прежнего snapshot описаны в
[ucm-publication.md](ucm-publication.md).

Миграция `0006_ucm_incremental_indexing.sql` сохраняет profile анализа, file
ownership и reverse dependency metadata по snapshot. Эти manifests становятся
immutable вместе с canonical facts. API описан в
[ucm-incremental.md](ucm-incremental.md).

Миграция `0007_ucm_legacy_migration.sql` добавляет explicit legacy/UCM repository
mapping, persistent read selection и immutable compatibility projections.
Таблицы repos/nodes/edges/data_* сохраняются. См.
[ucm-legacy-migration.md](ucm-legacy-migration.md).

Миграция `0008_sql_candidates_construction.sql` добавляет SQL_CONSTRUCTION,
две registry relations и нормализованные constructions/variants/fragments/reasons
с snapshot-scoped FK и immutable guards. См. [sql-construction.md](sql-construction.md).

Миграция `0009_sql_execution_sinks.sql` добавляет SQL_EXECUTE, typed execution
records и relations EXECUTES_SQL/USES_SQL_CONSTRUCTION. Контракт:
[sql-execution.md](sql-execution.md).

Миграция `0010_sql_semantic_access_analysis.sql` вводит SQL_STATEMENT/DATA_ACCESS,
statement/reason/access/name tables и semantic relation registry. Имена и quoted
flags нормализованы в columns, SQL AST не является opaque JSONB payload.
См. [sql-semantics.md](sql-semantics.md).

Миграция `0011_sql_parameter_lineage.sql` добавляет typed placeholders/bindings,
ordered reasons и lineage registry pairs, snapshot-scoped FK и immutable guards.
См. [sql-lineage.md](sql-lineage.md).

Миграция `0012_database_schema_identity.sql` вводит independent versioned database
inventory и file-owned UCM projections/contextual resolutions. Imports атомарны,
READY versions immutable; global identity включает database/version и name parts.
Legacy data_* остаются. См. [database-identity.md](database-identity.md).

Миграция `0013_jpa_orm_semantic_analysis.sql` вводит ORM_MAPPING/QUERY/OPERATION,
typed names/reasons, owner/CALL/query/context FK и ORM relation registry.
SQL/native pipeline переиспользует существующие canonical tables; JPQL не
создаёт physical SQL execution. См. [jpa-orm.md](jpa-orm.md).

Миграция `0014_source_adapter_registry.sql` вводит SOURCE_ANALYSIS и normalized
per-file adapter profiles/capabilities/reasons/diagnostics. Reports immutable вместе
с snapshot; runtime registration не хранится arbitrary JSONB. См.
[source-adapters.md](source-adapters.md).

Миграция `0015_per_adapter_invalidation.sql` вводит `ingest_snapshot_adapters`:
версия и fingerprint каждого адаптера в snapshot, immutable с VALIDATING. См.
[ucm-incremental.md](ucm-incremental.md).

Миграция `0016_ingest_jobs_recovery.sql` вводит `ingest_jobs` и разрешает очистке
удалять факты RETIRED snapshots под флагом `code_crawler.gc`. См.
[ingest-jobs.md](ingest-jobs.md).
Миграция `0017_reproducible_source_evidence.sql`: exact source blobs, snapshot links,
immutability/checksums, обязательный архив перед READY/PUBLISHED и явная
совместимость старых published snapshots. Новые clean/dirty captures архивируются
в PostgreSQL без внешнего blob store/расширений: [source-evidence.md](source-evidence.md).

Миграция `0018_ucm_query_indexes.sql` добавляет четыре B-tree индекса под запросы
структурного поиска. См. [query-indexes.md](query-indexes.md).

Миграция `0019_lexical_search_index.sql` ставит расширения `pg_trgm` и `btree_gin`,
вводит функцию `ucm_identifier_words` и три GIN-индекса лексического поиска. См.
[lexical-search.md](lexical-search.md).
