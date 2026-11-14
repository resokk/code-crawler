# Java call resolution

`java_calls.JavaCallAnalyzer(tuple[SourceInput,...])` строит замкнутый каталог
Java types/methods репозитория и является callback для index_incremental.
`index_java(conn, repo, root)` выполняет capture и подключает его автоматически.
Передавайте analyzer.analysis_version: он включает fingerprint классов, imports,
сигнатур, return types и modifiers. Изменение каталога вызывает full rebuild;
body edits используют прежние file dependency правила. Подготовка каталога пока
разбирает все Java files; это ограничение нового adapter, не generic incremental API.

Разрешаются method_invocation внутри explicit method/constructor: unqualified,
this, параметры/locals/fields с известным type, explicit static class receivers и
chained calls с разрешённым return type. Поиск выполняется в repository catalog,
не в других репозиториях. Поддержаны package/single-type imports и локальные
nested names; неизвестные wildcard imports остаются неопределёнными.

Применимость проверяется по arity и типам литералов/идентификаторов/casts/new/
разрешённых nested calls. Поддержаны exact types, primitive widening и Object
reference conversion. Победитель должен быть единственным и доминировать по всем
conversion positions; unknown conversion не получает угаданную стоимость.
Unknown arguments, generics, varargs expansion, boxing, inheritance и сложная
reference assignability дают PARTIAL/AMBIGUOUS без подтверждённого target.
Private/cross-package доступ и static receiver проверяются в поддерживаемых случаях.
Это не компилятор: classpath, protected/nestmate rules и runtime virtual dispatch
не моделируются, Coverage всегда PARTIAL, resolved CALLS имеет INFERRED certainty.

Occurrence CALL и его REFERENCES обновляются согласованно с локальным result;
CALLS идёт от caller Symbol к выбранному Method либо сохраняет candidates/status.
Для PARTIAL relation occurrence остаётся UNRESOLVED (старый контракт не имеет
PARTIAL). Неразрешённая внешняя/неизвестная цель без local candidates получает
ExternalReference и локальную EXTERNAL_DEPENDENCY, не cross-repository edge.
Selector не выдаёт типы фактических аргументов за объявленную signature.

Evidence содержит точный invocation SourceRange и версию resolver. Calls в
initializers, constructor invocations/implicit constructors и исключённых
java.symbols поддеревьях не становятся подтверждёнными CALLS. SQL execution
не выводится из method name. Legacy CLI/compatibility reader не переключаются.
Диагностики Java останавливают canonical callback; прежний snapshot сохраняется.

Инициализируйте UCM repository через snapshots.register_repository, затем вызовите
`result = await index_java(conn, repo, root)`, `validate_snapshot` и
`publish_snapshot(..., expected_snapshot_id=result.base_snapshot_id)`.
При самостоятельной работе с JavaCallAnalyzer передавайте ровно его
analysis_version; generic orchestrator проверяет этот optional adapter contract.
Single static imports поддержаны для известных local methods/types; неизвестные
static member namespaces и local type receivers не получают угаданной type binding.
