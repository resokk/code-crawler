# Реестр readiness-инвариантов (B02)

`UcmBatch` остаётся reference validator для полного набора моделей.
`publication.validate_snapshot` применяет те же модельные и локальные cross-entity
правила порциями; глобальные множества и all-SQL hydration заменены запросами
`snapshot_validation`. Все запросы ограничены одним snapshot, выбранным API.

| Инвариант reference validator | Readiness implementation |
| --- | --- |
| Уникальный entity ID, envelope/subtype type, repository ownership | PK/FK storage; строгий `Entity` TypeAdapter в `_parse`; `check_entities` |
| Logical ID соответствует repository/type/logical_key; contract version, enums, scalar shapes | Те же `EntityEnvelope` и subtype model validators, JSON strict mode |
| Подтипы полны; нет лишних subtype/auxiliary rows | `_documents` для каждой порции и итоговый `consumed` Counter по фиксированному реестру таблиц против SQL count |
| Ordered arguments, candidates, variants, fragments, reasons, Evidence ordinal | `_ordered` и `_documents`, как в whole-batch restore; snapshot-wide Python state не нужен |
| SourceFile canonical path/hash; SourceAnalysis capabilities/diagnostics | Те же вложенные модели; uniqueness path/report — `check_global_invariants` и UNIQUE storage |
| Scope parent/owner, Symbol scope/type/signature, Occurrence scope/target, Operation scope/inputs/outputs/callee, Value type | Общий `check_entities`, lazy catalog, typed FK |
| Value имеет не более одного producer, включая повтор одного output внутри operation | SQL GROUP BY output value_id с COUNT(*) > 1; reference сохраняет set-based проверку |
| Parent-scope graph ацикличен | SQL temporary parent map, pointer doubling за <= bit_length(N) раундов; reference `check_scope_cycles` |
| Ближайший callable ancestor для SQL/ORM invocation | Общий constant-space `_callable_owner` с Floyd cycle detection, lazy LRU catalog |
| SQL construction owner; local SQL_CANDIDATE; fragment file references | Общий `check_entities`, `SqlConstruction`/`SqlVariant` validators |
| Candidate имеет единственного construction owner; statement position и placeholder ordinal уникальны | SQL GROUP BY и существующие UNIQUE constraints, ключи совпадают с reference |
| Statement text соответствует срезу variant | SQL substring с start+1 и length=end-start; Python и PostgreSQL считают Unicode characters, не UTF-8 bytes |
| Partial variant допускает только PARTIAL statement и не допускает DataAccess | Два SQL EXISTS check в `check_sql_semantics` |
| Execution statement принадлежит construction descriptor execution | Normalized target/candidate SQL links + variants membership |
| RESOLVED execution statement требует RESOLVED origin, ровно один allowed candidate и COMPLETE statement | SQL checks resolution, DISTINCT candidate count и parse_status; certainty не изменяется |
| Один USES_SQL_CONSTRUCTION descriptor на execution | Общая новая duplicate check в reference и SQL GROUP BY (см. совместимость ниже) |
| Placeholder принадлежит COMPLETE statement и соответствует token slice | Общий `check_entities` и `SqlPlaceholder` model |
| Binding setter — CALL нужного API; JDBC selector/value/setNull согласованы с inputs | Общий `check_entities`, дочитывание только нужных Operation/Value |
| BINDS_PARAMETER target принадлежит statement данного execution | SQL membership через EXECUTES_STATEMENT targets/candidates |
| Binding position/name совпадает с placeholder; definite link требует BOUND | SQL kind/selector/status checks; UNRESOLVED без targets не получает выдуманных связей |
| DataAccess не утверждается для failed/unsupported statement; effect relation соответствует statement/access_kind | Общий `check_entities` и `validate_relation_endpoints` |
| Database projection/source file, context search path и database object identity | Общие модели, `check_entities`, inventory FK |
| DatabaseAccess execution/statement/context membership | SQL membership EXECUTES_STATEMENT и USES_DATABASE_CONTEXT |
| Contextualizes/context/DB target kind и database/version/fingerprint согласованы | Общий `validate_relation_endpoints` с lazy catalog |
| ORM class/attribute ownership, getter/field scope, query owner, CALL/API/invocation scope | Общий `check_entities`, `OrmMapping`/`OrmQuery`/`OrmOperation` model validators |
| ORM named query, entity/attribute targets, captured query, native/context DB version | Общий `validate_relation_endpoints`; никакого независимого упрощённого ORM validator |
| Relation/ExternalReference endpoints local, declared type, source/target kinds, Evidence file, Coverage/certainty | Общие `validate_relation_endpoints` / `validate_external_reference` и strict models, включая BPMN/Kafka/OpenAPI rules |
| Archived source bytes полны и соответствуют SourceFile hashes | Существующий `require_source_archive`, до freeze/READY; legacy provenance rules сохранены |
| READY/receipt только после всех проверок | Freeze transaction → pinned REPEATABLE READ scan → final row-lock/state check и atomic receipt+READY |

Реестр не заявляет доказательство истинности статического анализа или соответствия
имени Java-метода тексту исходника. Как и reference validator, structural Evidence
проверяет существование файла и корректную форму диапазона; source archive —
полноту/хеш. Уровень Certainty остаётся сохранённым фактом анализатора.

## Совместимость и границы

Ранее несколько USES_SQL_CONSTRUCTION relations от одного execution выбирались
Python dict по правилу «последний победил», зависящему от порядка чтения. B02
отклоняет такой недетерминированный набор в обоих путях. Это усиление проверки,
а не выбор/слияние origin candidates. Адаптер должен выразить альтернативы одним
PARTIAL/AMBIGUOUS descriptor. Остальные правила переиспользованы либо перенесены
в SQL с parity tests. Существующие READY/PUBLISHED receipts и immutable факты не
переписываются. Публичные UCM entities и ingest/publication signatures сохранены.

Readiness держит порцию из 2000 entities и LRU максимум 20000 моделей. Дочитывается
один hop, порциями не более `_SLICE`; транзитивное раскрытие графа больше не
собирает всю компоненту. Paths/producers/reports/parent graph/SQL facts не
накапливаются в Python. Временные SQL parent/link projections содержат только
идентификаторы/статусы и удаляются с транзакцией. Их disk space пропорционален
графу; PostgreSQL memory/spill определяется work_mem, maintenance_work_mem и
temp_buffers. Это не абсолютная квота всего RSS сервера или размера одной entity.
Нефиксированный nested payload одного construction/Relation по-прежнему должен
поместиться в память как одна модель.

В фазе scan нет FOR UPDATE lock repository; есть REPEATABLE READ transaction и
shared snapshot lease. B02 не сокращает срок жизни MVCC view (это отдельный B03).
При cancellation validator останавливает дальнейшие reference reads и дожидается
завершения уже запущенного worker thread перед rollback/освобождением соединения.
Ошибка оставляет VALIDATING без нового receipt. Если другой validator уже создал
READY, возвращается его сохранённый count; если snapshot уже опубликован/сменил
состояние, текущий вызов не создаёт receipt и сообщает state changed.

Permanent schema не меняется: новая миграция не требуется. Прямое отключение
constraints/guards владельцем БД не входит в модель защиты readiness.

## Проверка SQL-dense памяти и времени

[Полные observations, settings и source hashes](benchmarks/bounded-validation-pg15-2026-11-16.json).
Baseline — `2951af8`, до B02. Отдельные свежие процессы и disposable PG15 databases;
никакие тесты/другой benchmark не выполнялись параллельно с этими наблюдениями.
Linux x86_64, quota 2 CPU / 8 GiB RAM, Docker PG15.20, PGDATA 5-GiB tmpfs,
shared_buffers=128MB, work_mem=4MB, locale en_US.utf8. Ingestion/archive выполняются
до начала отсчёта readiness/tracemalloc; parser не вызывается.

Fixture содержит N независимых candidate/construction/statement/access units,
один SourceFile и owner Symbol: 4*N+2 entities, 3*N SQL-моделей плюс normalized
variants/fragments/names. SQL содержит Unicode emoji и quoted `"Users"`, чтобы
проверять character slicing и exact identifier preservation. Прочие SQL binding,
context, partial/ambiguous/failed и ORM правила покрываются parity fixtures.

До окончательного замера зафиксирован критерий: при росте SQL facts в 4 раза
пик Python heap readiness растёт менее чем в 1.5 раза и остаётся ниже 128 MiB
на этой fixture. Это проверка scaling, не byte-квота для произвольной модели.

| Вариант | Entities | SQL models | Readiness с tracemalloc, с | Python heap peak, MiB | Process peak RSS, MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 24002 | 18000 | 18.840 | 63.76 | 207.10 |
| baseline | 96002 | 72000 | 88.508 | 221.58 | 643.48 |
| B02 | 24002 | 18000 | 11.997 | 42.95 | 123.28 |
| B02 | 96002 | 72000 | 55.276 | 40.38 | 127.54 |

Growth factor heap B02 — 0.94, baseline — 3.48. Лимит 128 MiB соблюдён. Порция
2000 и cache 20000 — production defaults в обоих вариантах. RSS включает фазу
подготовки/ingestion и стоимость tracer; это не чистый heap validation и не RSS
PostgreSQL. Отдельные no-trace наблюдения на 96002 entities: baseline 22.318 с /
321.07 MiB process peak RSS, B02 12.707 с / 92.09 MiB. По одному наблюдению на
конфигурацию не определяется SLA или статистически гарантированный speedup.

Воспроизводимые команды (BENCHMARK_DATABASE_URL — выделенный PG15 admin с CREATEDB):

```bash
uv run python -m code_crawler.validation_benchmark --units 6000 --output small.json
uv run python -m code_crawler.validation_benchmark --units 24000 --output large.json
uv run python -m code_crawler.validation_benchmark --units 24000 --no-trace --output wall.json
```

Для baseline тот же harness запускается с кодом `2951af8`, например копированием
`validation_benchmark.py` в detached checkout и PYTHONPATH на его src. Benchmark
создаёт/удаляет только собственную `crawler_validation_<uuid>` базу; проверяет
READY/receipt через обычный validate_snapshot и возвращённый count. Между runs
ничего не переиспользуется. Следующий main добавил B01 benchmark runner, не меняя
измеренные ingestion/publication modules или schema; итоговые tests/CI включают B01.

Автоматическая уменьшенная scaling fixture использует фиксированные slice64 /
cache128, 1002 → 4002 entities и threshold 1.5. Она падает на baseline: 9320231
bytes > 3006458*1.5; проходит на B02. Отдельный тест гарантирует отсутствие N+1
catalog reads при помещающемся direct-reference working set: refs собираются
до `_parse` (он расходует rows), cache hits помечаются hot до prefetch misses.
Полный reference loader сохраняет намеренную возможность материализовать весь
набор. Для legacy graphs с несколькими construction descriptors он теперь тоже
отклоняет недетерминированную семантику; обычный per-entity reader и старые receipts
не переписываются.

Validator role требует TEMP privilege, уже необходимый ingestion writer.
Транзакция scan не является read-only из-за session-local temporary DDL; canonical
факты в ней только читаются. При отмене не планируется следующая порция reference
reads; текущий worker/read завершается перед освобождением transaction и lease.
