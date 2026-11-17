# План развития code-crawler v4 — 17 ноября 2026

**Baseline:** `main@e133cccb65a39fa62615cc484441a6f523ec6973`. Основание — [новое code review](review-2026-11-17-e133ccc.md). Прежний [план v3](development-plan-v3.md) сохранить для истории; **не переписывать завершённые changes**.

## Завершено с предыдущего ревью

A02, A03, A04, A06, B01, B02, B03, B04, E01, Java SQL flow COW, Java source-text cache, configurable SQL-path budget; canonical UCM, C01–C06, D01/D02, D05/D06, D07, D10/D11/D12 уже были. Подтвержден CI на текущем SHA и архивы completion. B02 больше не имеет прежнего all-SQL Python hydration, B03 не держит CPU parsing внутри write transaction. Никакой новый change не должен повторно реализовывать эти действия.

## Волна 0. Сохранность существующих развёртываний (P1 — первой)

### A07 migration-history-and-schema-resolution (НОВОЕ)

**Цель:** доказать upgrade существующей БД после редактирования миграций 0003–0029, определить единую политику schema/search_path и защитить историю миграций от дальнейшего незаметного изменения.

**Крупные критерии:**
- сохранивший данные старый PG15 instance обновляется до `main` с сохранением published snapshot, FK/Evidence, search и ACL;
- fresh init и upgrade дают согласованную схему; отличия диагностируются, но не «исправляются» тихой перезаписью БД;
- будущая правка уже применённого migration-файла обнаруживается проверкой checksum/manifest;
- нестандартный `search_path` не создаёт незаметно таблицы не в выбранной схеме;
- новое правило не требует автоматического replay исторических SQL и не удаляет данные.

**Разрезать на 3 маленьких изменения для LLM:** `a07-upgrade-fixtures` (old populated DB → current), `a07-migration-checksums` (legacy hashes + future immutability), `a07-schema-context` (search_path contract, strict tests). Детали в [A07 OpenSpec](../openspec/changes/a07-migration-history-and-schema-resolution/).

### A05 required-main-ci-check (P1)

Нужна отдельная административная проверка: no-bypass branch rule, required PR, негативные сценарии failing/missing/successful checks. Не закрывать потому, что CI зелёный.

## Волна 1. Измеренные эксплуатационные проблемы (P1)

| Порядок | Change | Содержание | Acceptance |
| --- | --- | --- | --- |
| 1 | **B06** large-snapshot-gc-performance | FK-trigger/index планы, GC duration, WAL, locks, dead tuples, 100k/1M; безопасная очистка без чужих таблиц и pinned snapshots | Новые PG15 замеры существенно лучше 120s timeout на сравнимом fixture; целевой SLO утвердить после baseline |
| 2 | **E02** snapshot-retention-policy | CURRENT/RETIRED/PINNED/FAILED, shared content blobs, derived generations, dry-run, retention pins | Нельзя удалить shared blob/pinned snapshot; orphan blobs очищаются только после доказанного отсутствия ссылок |
| 3 | **C12** streaming-search-document-rebuild | Удалить `load_snapshot_batch` + большой `_records` из C01 projector, streaming COPY и atomic generation | Документы/хеши совпадают со старым projector; bounded RSS на >1M fixture; rollback |
| 4 | **B05** incremental-streaming-pipeline | Лимит bytes/entities/temporary storage в spool/staging, no-change clone, memory/disk/cancellation tests | Предсказуемые resource budgets, корректный source fingerprint и неизменный published pointer при сбое |
| 5 | **B07/B08** mixed-language and 100+ repositories | Реальные mixed-fixtures, concurrent queries/index/publish/GC, зафиксированные latency/memory/IO | Независимые публикации, отсутствие репозиторных утечек; нагрузочные данные на PG15 |

B06 и A07 можно выполнять параллельно. E02 должен быть согласован до разрушительного GC на больших данных. Для B05 сначала использовать B03 benchmarks как текущий baseline: 72.03 → 25.11 секунд sampled transaction и 64 MB spool на 400 Java files.

## Волна 2. Завершение query-time discovery и MCP (P1/P2)

- **C10** Kafka topic discovery — реализовано, ожидает полный PG15 CI: **declarations only**, cluster/namespace identity, C04 candidate uncertainty, version-context compatibility.
- **C11** BPMN worker discovery — реализовано, ожидает полный PG15 CI: definite handler declaration vs external worker reference; ambiguous/partial без выдуманного runtime linkage.
- **C07** Embedding pipeline — выбрать модель для RU/EN code+SQL+schema, pgvector 0.8.0, model/preprocessing registry, redacted C01 input, content-hash cache, generation lifecycle. Ресурсы inference измерить на целевом железе.
- **C08** Hybrid retrieval — exact/FTS/trigram/vector + bounded graph expansion, explainable ranking, тестовый RU/EN retrieval dataset.
- **C09** Multi-repo MCP — global search, explainable resolution, bounded backward impact; строго ACL A02 и контекст C03. Никаких глобальных canonical relations.

Приоритет C10/C11 зависит от того, нужны ли Kafka/BPMN сценарии для ближайшего пользовательского поиска. Начать C07 можно параллельно с C12, но C08 требует устойчивых persisted documents и безопасной политики A06.

## Волна 3. Бизнес-источники и эксплуатация (P2)

- **D03→D04** `<type>-data.json` → ReferenceDataset/Field/Record → loader SQL/ORM → DB column с Evidence и оговоркой про deployment.
- **D08→D09** GraphQL SDL/introspection → schema types/root/fields → Spring GraphQL/DataFetcher bindings и локальные Java CALLS.
- **E03** disaster recovery: pg_dump/restore/retained versions/source archive/search+resolver generation, retry, CRC/source hash, isolated PG15 rehearsal.
- **E04** OpenSpec archiving и documentation hygiene; все completion receipts сохранять.
- **Language quality**: реальные coverage fixtures для Kotlin JS/TS VBScript, Java-path truncated cases и differential SQL analysis (без претензии на полное runtime покрытие).

## Выполнение LLM среднего уровня

Каждый change = одна независимая capability/ошибка; при необходимости делить B05/B06/C07 на небольшие подchanges. Нормативные `MUST` и Given/When/Then, минимум один негативный сценарий, точный scope, обработка ошибок, PG15 CI при изменениях БД, benchmark при performance change. Не менять применённые миграции; создавать forward-only миграции. Явно сохранять `Certainty / Resolution / Coverage / Evidence`. Никаких ложных confirmed SQL execution, physical DB target, Kafka/BPMN runtime или межрепозиторных edges.

## Контрольные точки

1. **Migration-safe release:** A07 upgrade fixture, исторический schema resolver и A05 policy.
2. **Operationally predictable storage:** B06 + E02 + C12 + B05, исключение неограниченных временных файлов/GC latency; pin-safe behavior.
3. **Search-ready GraphRAG:** C07→C08→C09, coverage и корректные version contexts.
4. **Business workflows:** D03/D04 + D08/D09, end-to-end trace до Java/SQL с Evidence.
5. **Fleet scale:** B07/B08 + E03, подтверждённые 100+ repo benchmarks и restore.
