# Инкрементальная индексация UCM

`index_incremental(conn, repository_id, root, analyze, *, languages, analysis_version)`
строит новый BUILDING snapshot, используя текущий опубликованный как baseline.
Legacy CLI пока не переключается: вызов предназначен для UCM adapters, которые
получают tuple SourceInput(file: SourceFile, content: bytes) и возвращают tuple
FileAnalysis(path, entities, dependencies). Анализатор вызывается один раз только
для выбранных файлов; пустой набор не вызывает callback. SourceFile создаёт
orchestrator; analyzer возвращает остальные сущности и явные file dependencies.
Каждая сущность имеет ровно один файл-владелец. Shared/global entities должны
получать единственного владельца, а не дублироваться во всех файлах.

Inventory включает все tracked regular files Git, включая metadata/config;
untracked, symlinks (в том числе через symlink directory), submodules и отсутствующие
файлы не читаются. languages задаёт mapping конечного suffix→language (например,
{'.java': 'java'}); файлы без adapter получают SourceFile language='unknown', но
не передаются analyze. Git conflicts отклоняются. Root обязан быть корнем Git.
Пути и dependencies — canonical relative POSIX paths без traversal.

Git diff --name-only -z --no-renames между baseline commit и текущим HEAD даёт
список Git changes в плане. Авторитетны SHA-256 фактических bytes и language:
они выявляют также staged/unstaged изменения при неизменном HEAD. Если baseline
commit больше недоступен, достаточно fingerprint inventory. Rename трактуется
как delete+add. Source fingerprint snapshot вычисляется из canonical JSON списка
[path,content_sha256,language], отсортированного по path.

Изменения/добавления/удаления запускают транзитивную invalidation по прежним
зависимостям dependent→dependency. Зависимости включают явные adapter dependencies
и структурные ссылки между сущностями разных файлов (включая Evidence).
Отсутствующая dependency допустима как negative dependency: появление tracked
файла позже инвалидирует dependent. Внешние репозитории не участвуют.

Переиспользование допускается только с полным persisted file ownership/dependency
manifest и тем же analysis_version/languages. Изменение профиля или baseline без
manifest вызывает полный переразбор поддерживаемых файлов. Версия должна учитывать
изменения parser/resolver/config semantics. Незаявленные динамические зависимости
не угадываются: полнота explicit dependency extraction — обязанность adapter.

Перед записью повторно проверяются HEAD, branch, dirty и inventory fingerprint;
если исходники изменились во время анализа, операция отклоняется. Анализатор
должен использовать переданные immutable bytes. При file read также проверяется
стабильность stat. Это не filesystem snapshot: транзитные изменения, вернувшиеся
к тем же bytes между проверками, не обнаруживаются.

Старые facts изменённых/удалённых файлов исключаются, остальные берутся из
immutable baseline; SourceFile заново формируются из текущих bytes. Итоговый UcmBatch
проходит полную validation. Отсутствующая/неверная ссылка не заменяется старым
фактом. Ошибка parser, Git или validation не переключает публикацию.

Миграция 0006 добавляет ingest_snapshot_profiles, ingest_file_entities и
ingest_file_dependencies. Их записи immutable с VALIDATING, как canonical facts.
Canonical COPY и manifests фиксируются одной транзакцией. Пустой BUILDING
snapshot metadata может остаться после DB failure; частичных facts/manifests нет.
Результат содержит snapshot_id, base_snapshot_id и IncrementalPlan. Публикация
отдельная: validate_snapshot, затем publish_snapshot(expected_snapshot_id=base).
Если baseline pointer успел измениться, CAS не позволит затереть новую публикацию.

Переиспользуется разбор, но итоговый полный batch всё ещё читается/хранится в
памяти и загружается COPY в новый snapshot целиком. Server-side row cloning,
streaming, CLI switch и language-specific extraction/resolution — следующие
changes. Для полной локальной resolution adapter может использовать собственный
контекст; callback обязан вернуть факты каждого запрошенного файла ровно один раз.
