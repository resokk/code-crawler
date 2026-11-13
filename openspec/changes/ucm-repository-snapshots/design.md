# Решение

Миграция 0003 создаёт ucm_repositories, ucm_snapshots и ucm_repository_publications, не изменяя legacy tables. UUID генерируются Python uuid4 без расширений PostgreSQL. repository_key — явный стабильный внешний ключ регистрации, display_name допускает дубли. Автоматическая нормализация origins не вводится без надёжной политики идентичности.

register_repository выполняет INSERT ON CONFLICT DO NOTHING, затем отдельный SELECT в READ COMMITTED transaction: конкурентная регистрация одного ключа получает один UUID. Повтор не перезаписывает metadata. create_snapshot всегда создаёт новый BUILDING snapshot, сохраняет commit, optional branch, dirty и SHA-256 source_fingerprint. Fingerprint рассчитывает будущий ingestion, а не эта API.

Триггер запрещает начальное состояние кроме BUILDING, изменения metadata и недопустимые state transitions. Допускается только BUILDING→VALIDATING→READY→PUBLISHED→RETIRED и idempotent state update. Это защита metadata; таблицы содержимого и их immutable guards появятся позднее.

Pointer имеет repository PK и composite FK к snapshot того же repository. Создание нового snapshot не переключает указатель, published_snapshot читает исключительно его. FK запрещает удалить referenced snapshot. На этом шаге pointer гарантирует ownership, а не readiness/state consistency: API publication ещё отсутствует. Gate, атомарное согласование pointer/state, сериализация конкурентных публикаций и rollback реализуются change 11. В integration tests pointer задаётся SQL как fixture; production writer пока legacy.

Тесты используют изолированные PostgreSQL 15 базы. Проверяются история с одинаковым commit, dirty/detached metadata, неизменяемость, ownership, lifecycle, migration upgrade с legacy rows, конкурентная регистрация и прежний CLI. Схема не требует новых расширений.
