# Groovy UCM adapter

GroovySourceAdapter использует существующую ANTLR 4.13.2 грамматику, не генерирует
новый parser и не выполняет Groovy code. Captured UTF-8 bytes разбираются SLL-first,
при ошибке выполняется LL pass. Lexer/parser diagnostics структурированы; при
ошибках syntax/encoding semantic facts файла не выдаются, SourceAnalysis сохраняет
причины и coordinates. ANTLR character offsets переводятся в UTF-8 byte columns.

Canonical symbols/scopes/occurrences покрывают declared types, methods/constructors,
parameters, fields/locals, script owner/run и closure/block scopes. Default arguments,
traits, generated AST transforms, MOP/delegate/property dispatch не превращаются в
compiler/runtime proof. Calls сохраняют unresolved occurrences и typed
ExternalReferences с Evidence; property names не подменяются локальными переменными.

SQL discovery сохраняет literals, scoped final constants, single-initializer locals,
concatenations/GStrings и typed unknown fragments. Неполное control-flow/string
recovery явно partial. SQL statements/accesses используют существующий semantic
builder; Groovy calls вроде sql.execute не доказывают execution. Межъязыковое
linking, classpath, generated methods и Groovy SQL runtime sinks — вне coverage.

Adapter `groovy/1` включён в CLI `index-sources` вместе с выбранным Java profile.
Routes: `.groovy`, `.gvy`, `.gy`, `.gsh`, `.gradle`; `.gradle.kts` не перехватывается.
`adapters list` публикует descriptor, `--dialect` задаёт SQL dialect обоим producers.
Generated ANTLR sources и legacy `index` не изменяются. Миграция не нужна:
используются существующие UCM entities и SourceAnalysis storage.

Coverage: parser diagnostics COMPLETE для корректного UTF-8/Groovy; symbols,
references, SQL construction и SQL semantic access PARTIAL. Тип без явного
объявления — `groovy.dynamic`, а не доказанный Java Object. Script class/run —
синтетические source owners, не утверждение о compiled class. Call targets,
qualified properties, implicit closure `it` остаются unresolved. Нет generated
accessors, overloads default arguments, compact record constructors и classpath.

String recovery не выполняет arbitrary expressions. Числовое сложение не
подменяется конкатенацией; unary/call/lazy interpolation дают DYNAMIC fragments.
Любая запись в local invalidates его constant recovery, независимо от порядка;
циклы/catch/lambdas дополнительно отключают constant propagation файла.
Tuple declarations fail closed с диагностикой extraction; syntax-valid файл при
этом не объявляется полностью поддержанным. Branch alternatives и assignments
после initializer не моделируются. Partial SQL не выдаёт подтверждённые accesses.
SQL discovery не доказывает достижимость литерала или исполнение запроса.

Проверки: unit tests parser/ranges/scopes/recovery/registry и PostgreSQL integration
mixed Java/Groovy, normalized roundtrip, diagnostics, no-change reuse и invalidation.
