# Каноническое хранилище UCM

Миграция 0004 добавляет нормализованные таблицы в public рядом с legacy.
Ключ каждой сущности — (snapshot_id, entity_id); один logical ID может повторяться
в разных snapshots. ucm_entities содержит envelope, repository UUID и координаты.
Composite FK (repository_id, snapshot_id) запрещает смешивать репозитории.
Адаптеры используют str(repository UUID) как repository_id при вычислении UCM ID.

Таблицы расширений: ucm_source_files, ucm_symbols, ucm_scopes, ucm_occurrences,
ucm_operations, ucm_values, ucm_relations, ucm_external_references. Они имеют
фиксированный discriminator и FK к типу envelope. CLASS/METHOD/SQL_CANDIDATE
пока представлены envelope без расширения; детальные Symbol используют SYMBOL.

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
