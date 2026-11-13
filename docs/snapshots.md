# Репозитории и snapshots UCM

Change `ucm-repository-snapshots` вводит независимый от legacy реестр в public:
`ucm_repositories`, `ucm_snapshots`, `ucm_repository_publications`.
Legacy repos/nodes/edges/data_* не меняются, CLI пока использует прежний writer.

Репозиторий имеет UUID и уникальный repository_key — явный стабильный ключ,
задаваемый вызывающей стороной (например, каталог организации + project ID).
Имя display_name не уникально; basename не является идентичностью. source —
описание источника, не credential URL. Автоматического объединения SSH/HTTPS,
renamed origins и локальных checkout нет: они должны использовать один ключ.
Повторная регистрация ключа возвращает прежний UUID, не меняя metadata.

Snapshot имеет UUID, repository_id, commit_hash, branch (nullable),
source_fingerprint (SHA-256 фактически анализируемых исходников), dirty,
created_at и state. Fingerprint передаёт будущий ingestion; эта API не вычисляет
его и не считает commit достаточным описанием dirty worktree. Повтор одного
commit/fingerprint создаёт отдельный snapshot, история не перезаписывается.
Snapshot metadata неизменяемы с момента создания. Lifecycle:
BUILDING → VALIDATING → READY → PUBLISHED → RETIRED; переходы назад и пропуск
состояний запрещены триггером. Повторное присвоение того же state допустимо.

Publication pointer: одна строка на repository_id с snapshot_id и updated_at;
composite FK гарантирует принадлежность snapshot тому же репозиторию.
Новый snapshot не меняет pointer; чтение published_snapshot возвращает snapshot
через этот pointer, или None, если публикации нет.

Это фундамент хранения: здесь нет API публикации и проверки готовности
содержимого. Таблица pointer пока гарантирует только ownership, не согласование
со state. Короткая транзакция переключения, validation gate, concurrency и rollback
будут реализованы `ucm-atomic-publication`; производственный writer не должен
использовать pointer до этого change. В тестах pointer устанавливается SQL для
проверки схемы и чтения. State PUBLISHED сам по себе не делает snapshot видимым.
Удаление опубликованного snapshot запрещает FK (NO ACTION); retention и каскадная
очистка не вводятся. Канонические факты и защита их immutable content введены миграцией 0004 —
см. [ucm-storage.md](ucm-storage.md). Bulk ingestion появится следующим change.
