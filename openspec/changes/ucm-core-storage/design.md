# Решение

Envelope хранится в ucm_entities с PK(snapshot_id,entity_id), repository UUID и composite snapshot FK. entity_type ограничен UCM registry. Каждый детальный subtype имеет фиксированный discriminator и composite FK к envelope. Logical ID повторяется между snapshots, но не внутри одного snapshot. Связи scope/symbol, targets и file ranges — snapshot-scoped deferred FKs для двухпроходной загрузки в следующем change.

Нормативные свойства — колонки и таблицы: ucm_symbols, ucm_scopes, ucm_occurrences, ucm_operations, ucm_values, ucm_source_files. ucm_type_refs хранит TYPE/PARAMETER/RETURN/CALLEE и position, ucm_operation_values — ordered inputs/outputs. Только literal payload использует scalar JSONB; целый UCM документ в JSONB не хранится.

ucm_relations имеет kind, source/target ID и типы, resolution, reason, certainty и coverage. ucm_relation_candidates хранит потенциальные цели. Миграция фиксирует RelationKind matrix в ucm_relation_sources/endpoints; FK проверяет пары типов и наличие фактических endpoints. Python registry и SQL matrix сравниваются integration test.

ucm_external_references сохраняет source и три селектора отдельными колонками; CHECK не допускает смешение selectors, внешняя цель остаётся UNRESOLVED. ucm_evidence хранит ordered source ranges/analyzer/version/rule/description для RELATION/EXTERNAL_REFERENCE. ucm_coverage_reasons содержит ordered непустые причины.

Каждая каноническая таблица имеет row trigger: INSERT/UPDATE/DELETE только для BUILDING. Он берёт FOR SHARE lock snapshot, конфликтующий с обновлением state, поэтому transition не обгоняет незавершённую запись. UPDATE не переносит fact в другой snapshot. Statement-level TRUNCATE trigger запрещает обход row guards, включая CASCADE. State VALIDATING уже read-only. Retention/привилегированный DDL — вне данного change.

SQL проверяет локальные домены, FK, discriminator, source/target пары, ordered ranges и часть Resolution/Coverage инвариантов. Полнота subtype rows, minimum evidence/candidates/reasons, role/owner совместимость TypeRef, callable subtypes, вычисляемый ID, occurrence location и operation cardinality проверяются будущим batch validator до READY. Foundation допускает промежуточные неполные BUILDING batches; writer пока отсутствует.

Legacy migration tests проверяют upgrade с данными, прежний CLI и COPY. Канонические tests создают небольшой граф SQL fixtures; это проверка схемы, а не новая публичная writer API. Политика immutable content дополнит atomic publication gate в change 11.
