# Source adapter registry

Source adapters — independent UCM producers: immutable descriptor, versioned
capabilities, supported suffix/language routes, captured-byte prepare и async analyze.
Adapter не получает DB connection/root и не записывает facts; registry/orchestrator
владеет capture, validation, incremental storage и publication lifecycle.

Registry создаётся явно, без process-global registration/порядка import. Duplicate
adapter keys/exact suffix routes отклоняются; longest suffix match детерминирован
(.d.ts специфичнее .ts). Unknown files сохраняют SourceFile metadata, не получают
угаданный parser. Версии/descriptors/catalog profiles входят в analysis fingerprint.

SOURCE_ANALYSIS сохраняет per-file adapter/version/profile, actual capabilities и
structured diagnostics в snapshot. Mandatory SourceRange использует captured file ID
и byte coordinates; unknown location остаётся отсутствующей. Errors не исчезают
при reuse. Semantic/prepare failure не публикует partial snapshot; recovered partial
facts допускаются только профилем, который возвращает явные diagnostics/coverage.

## Контракт producer

`SourceAdapter.descriptor: AdapterDescriptor` задаёт key/version, SourceRoute
suffix/language, upper-bound Coverage declarations и допустимые EntityTypes.
SOURCE_FILE/SOURCE_ANALYSIS принадлежат orchestrator и запрещены в output types.
Descriptor immutable; порядок регистрации не выбирает parser при exact conflict.
Registration не загружает source bytes и не открывает DB connection.

`await adapter.prepare(tuple[SourceInput,...]) -> PreparedAdapter` получает все
routed sources языка/profile, включая пустой tuple. Подготовка строит repository-local
catalog и expose nonblank stable analysis_version. Sources — frozen SourceFile и
immutable bytes; hash/repository/path/language проверяются. CPU work должен быть
в worker thread, как у JavaSourceAdapter. Ambient filesystem/DB/network source reads
не входят в контракт; внешняя schema/configuration передаётся typed immutable input.

`await prepared(selected_sources) -> tuple[AdapterFileResult,...]` возвращает каждый
requested file ровно один раз. FileAnalysis содержит только normative entities и
canonical relative dependencies; metadata SourceFile supplies orchestrator.
Capabilities override, если задан, имеет тот же set/version и не превышает descriptor
coverage. Diagnostics — typed SourceDiagnostic; unknown location — None.
Relations/ExternalReferences обязаны использовать declared capability/version/
coverage, иметь existing UCM Evidence/Resolution и укладываться в per-file claims.

Registry перепроверяет serialization/IDs, entity types/repository, result cardinality,
source hashes/catalog identity, immutable descriptor/version, capability bounds и
range bounds всех facts/evidence относительно captured inventory. Diagnostic
range относится к своему file; cross-file semantic evidence допустим для known
captured files. Semantic closure/ownership/references дополнительно проверяет общий
UcmBatch/incremental loader. Явные negative file dependencies сохраняются как раньше.

## Reports и failures

SourceAnalysis logical ID стабилен по SourceFile/adapter key; версии/profile/actual
coverage и diagnostics являются snapshot content. При error diagnostics COMPLETE
file capabilities downgraded в PARTIAL с причиной. UNSUPPORTED capability не
маскируется пустым успешным result; profile может вернуть metadata-only analysis.
Missing/duplicate output, undeclared facts/coverage, bad ranges и version drift
дают AdapterError с adapter_key/stage/issues и original exception cause.

Java symbols profile разрешает recovered AST facts с explicit parser diagnostics.
Остальные Java profiles сохраняют прежний fail-fast на parser diagnostics при
catalog preparation; ошибка возвращается structured AdapterIssue(path, diagnostic),
без partial canonical publication. SQL candidate parse errors также присутствуют
в SourceAnalysis как `sql.CANDIDATE_PARSE_ERROR`; это diagnostic candidate recovery,
а не утверждение о невалидном Java compilation unit. Existing statement reasons
не удаляются. Failed prepare не создаёт новый snapshot; DB failure остаётся atomic
по правилам incremental loader. Publication не вызывается автоматически.

## Активация и CLI

```bash
uv run code-crawler adapters list
uv run code-crawler index-sources /path/to/repository --repository-key org/repo --java-profile orm
```

CLI активирует также `GroovySourceAdapter`: `.groovy/.gvy/.gy/.gsh/.gradle`,
а также `PlplusSourceAdapter` для `.plp`. PL/Plus сохраняет CFT selectors,
не подменяя их physical SQL effects: [plplus-ucm.md](plplus-ucm.md).
SQL dialect общий у Groovy и Java. Подробности: [groovy-ucm.md](groovy-ucm.md).

Java profiles: symbols, calls, sql, execution, semantic, lineage, database, orm.
Они альтернативны для `.java`: несколько одновременно дают exact suffix conflict.
`java_adapter_catalog()` только описывает доступные варианты. Все используют
существующие canonical Java analyzers; их semantic contracts не переписываются.

`--dialect postgres|mysql|tsql` используется semantic/lineage/database/orm profile;
низшие profiles требуют default postgres. `--naming-policy UNKNOWN|IDENTITY`
применяется к orm. `--connections PATH` — JSON list ConnectionAssignment с explicit
Symbol logical keys/ConnectionContext (см. [database-identity.md](database-identity.md)).
CLI загружает READY schema versions до создания adapter, а producer получает только
typed manifests. `index-sources` local Git root должен быть repository root. Вывод —
BUILDING snapshot_id; validate_snapshot/publish_snapshot остаются отдельными actions.
Legacy CLI `index` и existing index_java_* APIs продолжают работать без registry.

Programmatic activation:

```python
registry = AdapterRegistry((JavaSourceAdapter(profile="orm"), other_adapter))
result = await index_sources(conn, repository_id, root, registry)
```

Новый язык реализует descriptor/prepare/async call и conformance tests. Loader,
publication и file ownership не меняются. Registry не является arbitrary plugin
sandbox и не регистрирует future language support по одному suffix без producer.
Unknown/unregistered files сохраняются как metadata-only SourceFile language=unknown
при capture через index_sources; они не передаются parser callback.

## Маршруты и incremental identity

Поддержаны simple/compound suffixes, case-sensitive longest match. Например .d.ts
побеждает .ts независимо от adapter order. Exact duplicates/adapter key conflicts
отклоняются до prepare; path traversal и ambiguous implicit priorities отсутствуют.
Source capture и parsed-path planner используют одну source_language функцию.

`source.registry/1:` fingerprint канонически объединяет sorted descriptors и actual
prepared versions; order регистрации/routes/capability ordering не меняет identity.
Изменение descriptor/version/route/coverage/underlying catalog вызывает conservative
full profile invalidation. No-change route/profile переносит SOURCE_ANALYSIS вместе
с facts; JSON Schema и миграция 0014 обеспечивают immutable typed report storage.
Per-adapter fine-grained invalidation, dynamic plugin loading и cross-language
semantic linking не объявляются этим change.
