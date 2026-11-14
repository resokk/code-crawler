# SQL parameter lineage

Opt-in JavaLineageAnalyzer/index_java_lineage расширяет semantic graph цепочкой
Java Value → SQL_BINDING → SQL_PLACEHOLDER → DATA_ACCESS column. Placeholder и
binding — отдельные typed facts; binding относится к конкретному execution,
placeholder к statement. Quoted strings/comments и PostgreSQL JSON ? operators
не становятся параметрами. Decoded SQL offsets не являются Java byte mapping.

JDBC profile: PreparedStatement/CallableStatement set* whitelist, one-based
constant positions, setNull, last setter wins, clearParameters, local aliases,
reassignment/close/escape и bounded branches. Снимок bindings берётся на execute;
последующие setters не изменяют прежние executions. Unknown indices/handle origins,
batch queues и unsupported flow сохраняют причины неполноты.

Spring JDBC: поддерживаемые String SQL overloads, scalar varargs/inline Object[],
Map.of/singletonMap и локальные Map/MapSqlParameterSource с literal keys.
Unknown callbacks, maps, collection expansion и mutable containers за пределами
callable не получают guessed values. Positional/named selectors различаются.

Java literals и local reaching definitions сохраняются как Values; runtime
parameters/fields — SYMBOLIC с VALUE_OF relation. Неизвестное expression — UNKNOWN.
SQL column associations выводятся из comparison/assignment/INSERT VALUES AST;
ambiguous expressions/derived outputs остаются partial/unresolved. Database
object identity и actual runtime value/effects не доказываются.

## API и lifecycle

`sql_parameters.analyze_parameters(text, dialect="postgres", positional_start=0)`
возвращает ordered ParameterAnalysis. Позиции parser nodes привязываются к tokens
при разборе SQLGlot, а не регулярным выражением. Имена повторных `:name`
сохраняются отдельными placeholders. JDBC `?` нумеруются через все sequential
statements одного candidate; `$n`/T-SQL `@name` сохраняются как server parameters,
но не подменяют JDBC `?` или Spring `:name` при matching.

`index_java_lineage(conn, repository_id, root, dialect="postgres")` возвращает
BUILDING snapshot. Caller отдельно вызывает validate_snapshot/publish_snapshot.
Profile `java.sql.lineage/1:` включает semantic profile, dialect, SQLGlot version и
Java catalog fingerprint; file ownership/reuse сохраняют lineage facts без повторного
анализа неизменённых файлов. Миграция 0011 хранит placeholders/bindings/reasons
нормализованно; publication gate повторяет UcmBatch validation после restore.

## Binding state и неполнота

Поддержаны exact JDBC receiver types и whitelist parameter setters (не fetch/timeout
configuration). Literal/known local selectors one-based; последний setter побеждает
для своего slot. Missing slot создаёт MISSING binding с UNKNOWN Value. Unknown
index удаляет прежнюю определённость slots; close/escape/reassignment не переносят
старое состояние на другой handle. `setNull` даёт null Value отдельно от SQL type
argument. В Operation сохраняются реальные ordered setter inputs. Значения
фиксируются при setter, bindings — при execution.

Simple local declarations/assignments переносят reaching scalar definition.
Increment/decrement, compound expressions и неизвестные transformations не
сохраняют устаревший literal. Runtime parameters/this fields остаются SYMBOLIC;
`other.field` не разрешается по имени собственного поля. Branch-dependent binding
snapshots и loop paths помечены PARTIAL; SQL origin variants фильтруются по
captured preparation text/range, без definite cross-variant binding.

Spring profile поддерживает update/queryForMap/queryForRowSet scalar varargs,
queryForObject/queryForList с Class literal и inline Object[]. Callback/legacy
array overloads вне этих shapes сохраняют unknown state. Named profile поддерживает
Map.of/Collections.singletonMap, new Map/HashMap/MapSqlParameterSource, literal
put/addValue, aliases, clear/remove и unknown mutation invalidation. Known map
можно переиспользовать в нескольких executions; unknown calls могут invalidate
его contents. Collection expansion остаётся partial даже при известном name.

Column mapping ограничен comparisons/assignment/INSERT VALUES. Complex expressions
могут дать несколько candidate DataAccess; projection/subquery output без точного
соответствия остаётся unresolved. Partial/dynamic/error SQL не получает guessed
placeholders. Дополнительно действуют Java symbol/execution coverage limits:
wildcard imports, inheritance/classpath, lambdas, try-with-resources и unsupported
control-flow не расширяются этим change. Batch snapshots, interprocedural mutable
state, ORM bindings, actual DB schema/connection и runtime values — вне coverage.

Выбор БД и schema version реализован отдельным opt-in adapter:
[database-identity.md](database-identity.md). Lineage-only API не выбирает database
context автоматически и сохраняет прежние syntactic column references.

JPA query domain/handle semantics описаны в [jpa-orm.md](jpa-orm.md).
`setParameter` поддерживается как fluent query handle, но JPA parameter binding
lineage этим профилем не объявляется полной; JDBC/Spring binding contracts сохраняются.
