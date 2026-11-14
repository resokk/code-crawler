# План развития 2.0

Основание: статическое ревью `c451718`; в ходе ревью целевой PostgreSQL 15 не
проверялся. Приоритет: корректность и воспроизводимость → производительность →
поиск → расширение покрытия. Новая модель UCM, SQLGlot и JPA не перепроектируются.

## Проверенное состояние на 2026-11-14

R1 реализован: штатный `index` публикует canonical snapshot, typed reader читает
его в закреплённой транзакции, исходные байты архивируются, mixed-language e2e
проверяет публикацию, reuse и rollback. [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43612670068)
на `e8e5f18` прошёл 842 теста. Обязательность этого check в branch rules ещё не
подтверждена: API настроек репозитория возвращает HTTP 403.

R2 частично завершён: cache offsets, single capture, per-adapter invalidation,
query indexes и jobs/recovery реализованы и проверяются в PG15 CI. Streaming
loader существует, но основной incremental pipeline и validation ещё загружают
полный batch; проверка одного snapshot свыше 1 млн сущностей остаётся открытой.
Замеры планов запросов на PG15 фиксируются отдельно в [query-indexes.md](query-indexes.md).

R3 уже содержит structural search, lexical search, document projections и MCP.
Это не закрывает незавершённые масштабные проверки R2 или оставшиеся сценарии
отдельных changes. В `50a71ca` occurrences строятся по запросу вместо хранения
в Java catalog, а `be53229` ограничивает ORM base cache шестнадцатью файлами.
Следующий приоритет — повторный замер памяти после этих изменений, затем
подключение streaming к штатному pipeline, ограничение памяти validation
и нагрузочная проверка. Поэлементное восстановление snapshot в `6afccac` уже
уменьшает пик validation, но не устраняет полный batch.

## R1 — Надёжная canonical индексация (P0)

| Change | Результат |
| --- | --- |
| canonical-index-publication-cli | CLI validate/publish, index-sources --publish, optimistic concurrency |
| canonical-index-default-backend | canonical по умолчанию после релизных тестов; explicit legacy без ложных confirmed executes |
| reproducible-source-evidence | reproducible publication; dirty policy reject или content-addressed blobs, проверка SHA-256 |
| canonical-read-api | чтение published snapshot, entities/relations/SQL/bindings/Evidence без смешивания версий |
| mandatory-postgres-ci | PostgreSQL 15, migrations, обязательные integration tests, failure artifacts и generated-file checks |
| canonical-e2e-regressions | mixed Java/Groovy/PLPlus → publish → read, отсутствие ложного execution, reuse и rollback |

Порядок выполнения: publication CLI → source evidence → PostgreSQL CI → read API +
e2e → default backend. R1 завершён, когда canonical можно построить, проверить,
опубликовать и прочитать без обязательного legacy.

## R2 — Масштабирование (P1)

1. source-range-offset-cache — offsets строк один раз на файл; UTF-8 bounds и benchmark.
2. single-capture-source-pipeline — shared captured inventory без ослабления change detection.
3. per-adapter-incremental-invalidation — отдельные fingerprints, catalogs и зависимости языков.
4. streaming-ucm-ingestion — incremental typed facts/staging/forward refs, atomic publication, fault injection; batch loader сохраняется.
5. ucm-query-index-optimization — типовые запросы, EXPLAIN ANALYZE BUFFERS, B-tree/GIN, ingest cost и latency baseline.
6. ingest-jobs-recovery — stage/attempt/failure state, retry, abandoned BUILDING cleanup и retention.

## R3 — Поиск и MCP (P1)

1. structural-search-api — symbols/signatures, callers/callees, SQL execution, readers/writers, bounded graph traversal, Evidence/Coverage.
2. lexical-search-index — identifiers, pg_trgm/FTS, repository/snapshot/type filters, pagination/ranking.
3. search-document-projections — только факты UCM: Java, SQL, DB, call summaries, Groovy/PLPlus.
4. mcp-structural-tools — search_symbols, find_callers/find_callees, find_sql_executions,
   find_table_readers/find_table_writers, trace_dependency, get_evidence; published only, explicit uncertainty.

## R4 — Межрепозиторный поиск и GraphRAG (P1)

1. global-discovery-catalog — завершён bounded v1: published symbols, DB objects и BPMN processes; OpenAPI HTTP contracts — PARTIAL без runtime service binding; worker/reference/Kafka — UNSUPPORTED до появления typed producers. [Контракт](global-discovery-catalog.md).
2. query-time-reference-resolver — version contexts, namespace/type constraints, candidates/uncertainty, evidence paths, cache invalidation; без обязательного предварительного linking.
3. embedding-generation-pipeline — Qwen3/model registry, hashes/cache/queue, preprocessing versions, pgvector 0.8.0.
4. hybrid-retrieval — exact + lexical + vector ranking и graph expansion; confirmed/inferred отдельно.

C01 добавляет версионированное хранение поисковых документов и атомарную
пересборку для immutable snapshot: [контракт](search-documents.md). Это внутренний
API с обязательными authorization scope и redaction policy; автоматический запуск
и embeddings ещё не подключены. B02 bounded-memory остаётся открытым.

## R5 — Источники (P1/P2, после R1)

bpmn-ucm-adapter → bpmn-java-bindings; reference-data-adapter →
reference-data-load-analysis; openapi-ucm-adapter → openapi-java-bindings;
graphql-schema-adapter → graphql-resolver-bindings; отдельные Kotlin,
JavaScript, TypeScript и VBScript adapters. Все используют registry,
SourceAnalysis, Evidence, ingestion и lifecycle, без прямой зависимости от PostgreSQL.
Не требуется завершение R4.

D01 BPMN schema adapter завершён: XML facts, typed control-flow relations,
отложенные selectors и incremental publication. [Контракт](bpmn-schema.md),
[PG15 CI: 882 passed](https://github.com/resokk/code-crawler/actions/runs/43646257264).
D02 BPMN Java bindings завершён: локальные delegates/beans/workers, Evidence из
BPMN и Java, typed variable mappings с явной неопределённостью.
[Контракт](bpmn-java-bindings.md),
[PG15 CI: 997 passed](https://github.com/resokk/code-crawler/actions/runs/43650283341).

D05 OpenAPI contracts добавляет YAML/JSON discovery, typed syntax facts,
локальные references и deferred remote selectors: [контракт](openapi-contracts.md).
OpenAPI 3.0/3.1/3.2, QUERY/querystring и incremental lifecycle покрыты тестами;
Java bindings остаются отдельным D06.
[PG15 CI: 1028 passed](https://github.com/resokk/code-crawler/actions/runs/43681621831).

## R6 — Production readiness (P1/P2)

repository-access-control; snapshot-retention-and-gc; observability-and-metrics;
load-testing-100-repositories; backup-restore-validation; openspec-spec-history
(актуальные specs и архив completed changes).

## Definition of Done

Каждый change: proposal.md, design.md, specs/<capability>/spec.md и tasks.md.
Scope — одна проблема; normative requirements имеют Given/When/Then scenarios.
Нужны positive/negative tests, PostgreSQL migrations/integration tests при изменении
storage, отсутствие ложных definite relations и поломок опубликованных snapshots,
проверяемое повторное индексирование, обязательный CI и явные Coverage limitations.
Tasks завершаются только после тестов. R2 и R3 могут развиваться параллельно;
R5 зависит от стабильных R1 contracts. Новые адаптеры и embeddings не опережают R1.
