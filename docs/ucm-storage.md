# Каноническое хранилище UCM

Миграция 0004 добавляет нормализованные таблицы в public рядом с legacy.
Ключ каждой сущности — (snapshot_id, entity_id); один logical ID может повторяться
в разных snapshots. ucm_entities содержит envelope, repository UUID и координаты.
Composite FK (repository_id, snapshot_id) запрещает смешивать репозитории.
Адаптеры используют str(repository UUID) как repository_id при вычислении UCM ID.

Таблицы расширений: ucm_source_files, ucm_symbols, ucm_scopes, ucm_occurrences,
ucm_operations, ucm_values, ucm_relations, ucm_external_references. Они имеют
фиксированный discriminator и FK к типу envelope. CLASS/METHOD/SQL_CANDIDATE
представлены envelope; детальные Symbol используют SYMBOL. SQL_CANDIDATE может
иметь typed variant payload, описанный ниже.

ucm_type_refs хранит типы/параметры/return types и callee с resolution;
ucm_operation_values — упорядоченные inputs/outputs; ucm_relation_candidates —
кандидаты; ucm_evidence — координаты и происхождение факта; ucm_coverage_reasons —
причины неполноты. Signature сохраняется через наличие callable owner_key и
упорядоченные PARAMETER refs, включая ноль параметров. External selectors
хранятся отдельными типизированными колонками и parameter_type_names text[].
UNKNOWN signature отличается от пустого массива. Literal — единственный JSONB
payload: только scalar/null, не произвольный документ UCM.

Встроенный relation registry хранится в ucm_relation_sources и
ucm_relation_endpoints. FK проверяет source, resolved target и всех candidates
по EntityType; фактический тип конца подтверждается FK к ucm_entities.
Все ссылки на канонические сущности включают snapshot_id; локальные ссылки
не могут обратиться к другому snapshot. Циклические ссылки symbol/scope и
source ranges используют DEFERRABLE INITIALLY DEFERRED FK.

SQL checks проверяют домены, ordered ranges, resolution/target, certainty,
coverage status, selector shape и payload. Полнота extension rows, обязательное
Evidence, количество candidates/reasons, callable subtypes, кардинальности
операций и детерминированность ID дополняются Python/batch validation в
[ucm-ingestion.md](ucm-ingestion.md). Readiness gate реализован в [ucm-publication.md](ucm-publication.md).

Fact INSERT/UPDATE/DELETE допускаются только для BUILDING snapshot. Триггер
берёт FOR SHARE lock snapshot, поэтому переход состояния ждёт завершения записи.
Перенос fact между snapshots запрещён; TRUNCATE fact tables запрещён. С READY,
а также VALIDATING, PUBLISHED и RETIRED содержимое read-only. Это не запрет DDL
для владельца БД. Политика retention/cleanup будет отдельным изменением.
Migration не удаляет и не переключает legacy writer. Staging/COPY и ID mapping
реализованы в [ucm-ingestion.md](ucm-ingestion.md).

Миграция 0008 добавляет ucm_sql_constructions (owner Symbol), ucm_sql_variants
(candidate, construction, position, text, partial), ucm_sql_fragments (ordinal,
kind, text, optional range) и ucm_sql_partial_reasons (ordinal, reason).
Snapshot-scoped deferred FK и immutable guards применяются ко всем четырём
таблицам. Ingestion/COPY и readiness restore сохраняют порядок и проверяют
fragment/text, partial/reasons, ownership и registry endpoints. Старые candidate
envelopes без construction допустимы для compatibility; произвольного JSONB нет.

Миграция 0009 добавляет ucm_sql_executions (owner_symbol_id, operation_id, api,
nullable sql_argument_index), SQL_EXECUTE discriminator и execution registry pairs.
Deferred snapshot-scoped FK и immutable write/truncate guards соответствуют
остальным facts. Readiness restore повторно проверяет CALL kind, callee/api,
owner scope и argument index; SQL links используют обычные normalized relations.

Миграция 0010 добавляет ucm_sql_statements и ordered ucm_sql_statement_reasons,
ucm_data_accesses и ucm_sql_access_names (part, text, quoted, normalized).
SQL AST не сериализуется произвольным JSONB: оригинальный statement и типизированные
access facts хранятся раздельно. FK snapshot-scoped/deferred; write/truncate guards
защищают все четыре таблицы. Gate восстанавливает names/reasons и проверяет
candidate slices, effect relations и execution origin. SQL offsets — decoded
character positions, а не Java UTF-8 byte columns.

Миграция 0011 добавляет ucm_sql_placeholders, ucm_sql_bindings и ordered
ucm_sql_binding_reasons. Selector kinds/names/one-based positions, Value и setter
CALL links хранятся typed columns, без opaque JSONB. Snapshot-scoped deferred FK,
unique statement/ordinal и immutable write/truncate guards применяются ко всем
трём таблицам. Gate проверяет token slice, execution/statement membership,
selector/value input consistency и причины неполноты после restore.

Миграция 0012 добавляет независимые ucm_database_catalogs/schema_versions/
schema_objects: immutable READY versions, globally keyed schema/relation/column
inventory, parent FK и fingerprint. Code snapshots используют ucm_database_objects,
ucm_database_contexts, ordered ucm_database_search_paths и ucm_database_accesses.
Global inventory не принадлежит code snapshot; проекции имеют snapshot/file-owned
UCM IDs и FK к READY imported version/object. Guard запрещает изменения/import в
READY inventory; snapshot guards сохраняют прежнюю lifecycle защиту projections.

Миграция 0013 добавляет ucm_orm_mappings, typed ucm_orm_mapping_names,
ucm_orm_queries, ucm_orm_operations и ordered ucm_orm_reasons. Entity/attribute
symbols, CALL/query/context refs и registry endpoints snapshot-scoped/deferred.
Все пять таблиц имеют write/truncate immutable guards; readiness восстанавливает
names/reasons и повторяет owner/API/effect/query/database invariants.

Миграция 0014 добавляет ucm_source_analyses, ucm_source_analysis_capabilities,
ordered ucm_source_analysis_reasons и ucm_source_diagnostics. Adapter/version/profile,
coverage/status/reasons и optional diagnostic coordinates хранятся typed columns.
Unique snapshot/source_file, deferred FK и immutable write/truncate guards
применяются ко всем четырём таблицам. Restore/gate проверяет report identity,
capability uniqueness/reasons и error/complete contradiction.
