# Решение

SourceInput содержит immutable SourceFile и bytes. Callback analyze получает только выбранные файлы и возвращает FileAnalysis с non-SourceFile entities и explicit local dependencies. Каждый факт имеет одного owner file. Полный merged UcmBatch проверяется прежним валидатором; неразрешённые внешние зависимости остаются ExternalReference.

Inventory использует NUL-separated git ls-files --stage и только regular file modes; raw git_output не trim/decode filenames преждевременно. Root должен быть Git root, unresolved index conflicts отклоняются. Файлы открываются через dir_fd/O_NOFOLLOW по компонентам пути; symlink directories, symlink files и submodules не читаются. Проверяется stat stability. Async filesystem work выполняется в worker thread, subprocess Git — asyncio.

Git diff между проверенными commit OIDs используется для git_changed в плане, с --no-renames и NUL paths. File fingerprints из фактических bytes/language — источник истины для dirty/index изменений и history rewrite. Source fingerprint snapshot — SHA-256 canonical ordered inventory. Rename — delete+add; deleted owners не переносятся.

plan_changes строит reverse transitive closure зависимостей от added/changed/deleted paths. Persisted dependencies объединяют explicit FileAnalysis dependencies и все structural EntityRef/ID references между file owners, включая Evidence. Negative dependencies на отсутствующие пути сохраняются. Неподдерживаемые tracked metadata тоже имеют SourceFile и могут инвалидировать parser files.

Baseline берётся из publication pointer и читается load_snapshot_batch с полной проверкой. Повторное использование требует полного ownership manifest, совпадения source fingerprint и analyzer profile (analysis_version + sorted suffix/language mapping). Без профиля/при его изменении выполняется полный разбор поддерживаемых файлов. Повреждённый manifest не принимается. Reused owners сохраняют facts/dependencies; для выбранных файлов они заменяются. SourceFile всегда создаются из текущих bytes.

После callback HEAD/branch/dirty/inventory повторно проверяются; изменение останавливает build до создания нового snapshot. Итоговый UcmBatch должен быть замкнутым, без stale references. Facts и metadata ingest_snapshot_profiles/file_entities/file_dependencies загружаются одной транзакцией через существующий staging/COPY writer. Для этого extraction record writer вынесен во внутренний _ingest_records, сохраняя public ingest_batch semantics. Snapshot metadata может остаться пустым BUILDING после DB failure; facts/manifests откатываются вместе.

Manifest tables имеют composite snapshot/file/entity FKs, reverse dependency index и те же immutable guards с VALIDATING. Не меняем migrations 0001–0005. Validation/publication выполняются отдельно, CAS expected pointer берётся из IncrementalResult.base_snapshot_id. Построение от прежнего baseline при конкурентной публикации не сможет затереть новый pointer.

Оптимизируется разбор, а не размер итоговой записи: baseline/batch остаются в памяти, новый snapshot получает полный набор records. Полнота explicit dependency extraction и версионирование анализа — ответственность adapter. Границы source bytes и семантика анализа не доказываются. Legacy CLI/PLPlus extractor не меняются; их UCM migration будет отдельной задачей.
