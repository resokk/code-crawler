# Java symbols и occurrences

`java_symbols.extract(SourceInput)` переиспользует AST из java.analyze и возвращает
JavaSymbolsResult(analysis: FileAnalysis, diagnostics, coverage). Callback
`analyze_files` подключается к index_incremental с languages={'.java':'java'} и
явной analysis_version. Legacy java.parse/index и compatibility bridge не меняют
свою identity: переход к нормативным Java symbols осуществляется этим adapter.

Извлекаются named classes/interfaces/enums/records, методы, explicit constructors,
formal parameters, fields и обычные local variable declarations. Формируются
FILE/TYPE/CALLABLE/BLOCK Scope, DECLARATION occurrences, identifier/type references,
READ/WRITE и CALL occurrences. SourceRange берётся из AST в UTF-8 byte coordinates.
SourceInput hash обязан совпадать с bytes; parser diagnostics возвращаются caller.

Class ID зависит от FQN; callable key — owner class key, name и ordered parameter
names с syntactic generic erasure и array dimensions. Constructor name=<init>,
поэтому он не конфликтует с методом с именем класса. Varargs нормализуется в [];
post-name dimensions учитываются. Parameters используют callable key и ordinal,
fields — class key/name, locals — lexical scope key/name. Block keys используют
порядок блоков внутри scope, не абсолютные offsets. Body/comment edits сохраняют
method identity. Duplicate declaration keys отклоняются, а не сливаются.

Это syntax-level identity: imports, type-variable bounds, classpath и полная JLS
erasure/типизация ещё не разрешаются. TypeRefs сохраняются UNRESOLVED. Parameter
Symbol.type_ref сохраняет syntactic generic arguments, signature использует erasure.
Record components/compact constructors, annotation elements, lambdas,
catch/enhanced-for/resource scopes, switch, method references и anonymous classes
пока не поддерживаются. Callable bodies и initializers с pattern bindings
исключаются целиком, чтобы не выдать неверное lexical resolution.

В обычных scopes data identifiers разрешаются по ближайшему видимому параметру,
local или field; local становится видимым с конца имени декларации. this.field
разрешается только среди fields ближайшего TYPE, arbitraryReceiver.field остаётся
UNRESOLVED. Assignment даёт WRITE, compound assignment/update — READ и WRITE.
Method names дают CALL: единственная цель не считается подтверждённой без call
resolution; несколько одноимённых overloads дают AMBIGUOUS candidates в Relation.
Типы, imports и внешние ссылки здесь не связываются по совпадению строки.

DECLARATION получает DECLARES Relation к точному Symbol. Остальные occurrences
получают REFERENCES с Evidence/Resolution/Certainty/Coverage; разрешённая lexical
reference имеет INFERRED certainty. Не создаются CALLS edges и SQL execution.
Coverage всегда PARTIAL с явными ограничениями; parser errors добавляют причину.
Это не проверка компиляции, access control, definite assignment или overload
applicability. Unresolved occurrences не выбрасываются. Cross-file linking и
полнота Java imports/dependencies будут расширены java-call-resolution.


`extract` допускает частичные AST с явными diagnostics. `analyze_files` отклоняет
такие результаты до канонической записи: текущий FileAnalysis не сохраняет parser
diagnostics отдельным каналом. Legacy CLI по-прежнему сохраняет partial recovery
и errors в file attrs. Adapter предназначен только для java.symbols capability;
SQL facts пока не извлекаются, существующий legacy index/bridge остаётся доступен.
Пример UCM вызова: `index_incremental(conn, repo, root, analyze_files,
languages={'.java':'java'}, analysis_version='java.symbols/1')`.
