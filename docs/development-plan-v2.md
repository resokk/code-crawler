# План развития 2.0

Основание: статическое ревью `c451718`; в ходе ревью целевой PostgreSQL 15 не
проверялся. Приоритет: корректность и воспроизводимость → производительность →
поиск → расширение покрытия. Новая модель UCM, SQLGlot и JPA не перепроектируются.

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

1. global-discovery-catalog — published symbols, DB objects, HTTP, BPMN, reference data, Kafka.
2. query-time-reference-resolver — version contexts, namespace/type constraints, candidates/uncertainty, evidence paths, cache invalidation; без обязательного предварительного linking.
3. embedding-generation-pipeline — Qwen3/model registry, hashes/cache/queue, preprocessing versions, pgvector 0.8.0.
4. hybrid-retrieval — exact + lexical + vector ranking и graph expansion; confirmed/inferred отдельно.

## R5 — Источники (P1/P2, после R1)

bpmn-ucm-adapter → bpmn-java-bindings; reference-data-adapter →
reference-data-load-analysis; openapi-ucm-adapter → openapi-java-bindings;
graphql-schema-adapter → graphql-resolver-bindings; отдельные Kotlin,
JavaScript, TypeScript и VBScript adapters. Все используют registry,
SourceAnalysis, Evidence, ingestion и lifecycle, без прямой зависимости от PostgreSQL.
Не требуется завершение R4.

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
