# Canonical published reader

`reader.published_reader(conn, repository_key)` открывает read-only REPEATABLE READ
transaction и выбирает publication pointer ровно один раз. Контекст возвращает
PublishedReader с repository_id/snapshot_id. Все методы читают только этот snapshot,
даже при конкурентной публикации/retention. Контекст держит shared transaction
advisory lease выбранного snapshot: GC пропускает версию до завершения чтения,
включая concurrent publication. После выхода из контекста reader не используется;
lease освобождается автоматически. Передаётся free connection, вложенная transaction
запрещена.
В памяти процесса не сохраняется ни session state, ни snapshot graph cache.

```python
async with published_reader(conn, "org/repo") as view:
    entity = await view.get_entity(canonical_id)
    outgoing = await view.get_relations(entity.id, direction="out")
    proofs = await view.get_evidence(outgoing.items[0].id)
```

get_entity возвращает полную discriminated UCM Entity: Symbol/signature, SQL
construction/fragments, statement/reasons, access/names, bindings, database context
и другие существующие модели. Typed convenience methods: get_sql_statement,
get_data_access, get_sql_binding, get_sql_execute. ID отсутствующего/чужого Entity
или неверный kind — ValueError, без fallback к другой версии. Все IDs валидируются.

get_relations включает incoming resolved target **и candidates** или outgoing source;
сохраняет resolution/certainty/Coverage/Evidence без promotion. Фильтр kinds и limit
1..200, deterministic ID order; RelationPage содержит snapshot_id/items/truncated.
Одно получение может гидратировать лишь ограниченную страницу normalized facts,
не загружает UcmBatch всего snapshot и не повторяет анализ исходников. Incoming
lookup объединяет IDs из индексов target и candidate; не фильтрует весь snapshot
через `OR EXISTS`.

get_evidence принимает Relation/ExternalReference ID, возвращает Evidence вместе с
hash-verified raw source fragment и provenance. Архив старого snapshot может быть
UNAVAILABLE_LEGACY: это явный unavailable_reason, source=None. Integrity/range
ошибки не скрываются. Никакого filesystem fallback. Сами SourceRanges и Coverage
остаются в typed Entity. Архив и lifecycle: [source-evidence.md](source-evidence.md).

Reader использует тот же normalized document decoder, что publication validation;
индивидуальные модели валидируются без требования закрытого batch на каждой
странице. Cross-entity invariants были проверены при READY, published facts frozen.
Модели не расширяются и SQL storage не меняется. Structural search/MCP сохраняют
прежние проекции; MCP request transaction становится REPEATABLE READ для согласованности
нескольких SELECT внутри одного tool call. Отдельные stateless calls могут видеть
разные publications, их ответы содержат snapshot_id. Reader не добавляет auth.

Сквозная regression: [canonical-e2e.md](canonical-e2e.md).
