# SQL execution sinks

Opt-in JavaExecutionAnalyzer/index_java_execution расширяет SQL construction
фактами SQL_EXECUTE. EXECUTES_SQL связывает callable Symbol с execution site;
USES_SQL_CONSTRUCTION связывает execution с восстановленной конструкцией либо
сохраняет unresolved/partial причину. Execution означает статически найденный
вызов API, а не доказательство runtime reachability, commit или data effects.

Профиль распознаёт точные типы JDBC Statement/PreparedStatement/CallableStatement,
Connection.prepareStatement/prepareCall и Spring JdbcTemplate/JdbcOperations,
NamedParameterJdbcTemplate/NamedParameterJdbcOperations. Одноимённые local APIs,
unknown receivers, JPQL, ORM и custom subclasses не считаются sink.

JDBC execute/executeQuery/executeUpdate/executeLargeUpdate с SQL argument создают
execution; prepare* только сохраняет SQL для последующего no-arg execute*.
Локальные aliases, reassignment и lexical scopes учитываются в пределах callable.
Unknown/escaped/closed handle не получает guessed SQL. executeBatch фиксируется
как execution с unresolved SQL: queue semantics и bindings — отдельный coverage.
Spring query/queryForObject/queryForList/queryForMap/queryForRowSet/update/execute/batchUpdate
распознаются только с первым String SQL argument; callback-only overloads исключены.

Operation CALL сохраняет ordered argument Values и scope; SQL_EXECUTE содержит
owner_symbol_id, operation_id, api, nullable sql_argument_index. Значения аргументов
не являются parameter bindings. Evidence содержит invocation range и preparation
range, если известен. Ветви и loops наследуют partial recovery и bounded paths;
неподдержанная control flow не превращается в доказанный statement target.

Миграция 0009 добавляет typed execution table и registry pairs. Ingestion,
readiness validation/restore и incremental reuse используют общий UCM contract.
Legacy CLI writer и construction-only API не переключаются. SQL semantic AST,
EXECUTES_STATEMENT и syntactic effects доступны следующим opt-in adapter из
[sql-semantics.md](sql-semantics.md). Connection identity и lineage остаются
отдельными changes.

## Coverage и использование

`index_java_execution(conn, repository_id, root)` возвращает BUILDING snapshot;
caller отдельно вызывает validate_snapshot/publish_snapshot. Profile
`java.sql.execution/1:` включает construction/call catalog fingerprints и не
переиспользует construction-only manifests. No-change переносит execution facts
вместе с file ownership; смена receiver types в catalog инвалидирует анализ.

Типы требуют explicit imports или FQN; wildcard imports и inheritance не
разрешаются предположением. Поддержаны inline Connection.createStatement и
prepare* chains, var локальные handles, алиасы и assignment. Callback-only
Spring overloads исключены; для named-parameter APIs требуется parameters argument.
Batch update/executeBatch сохраняет execution с неизвестной queue, без связи
с произвольно выбранной SQL строкой.

Действуют границы Java symbol adapter: lambda, try-with-resources, catch,
enhanced-for, switch и anonymous bodies не анализируются полноценно. Если
switch/catch/finally/enhanced-loop могут влиять на origin в callable, связь SQL
остаётся unresolved (direct literal не требует такого flow recovery). Обычные
if branches сохраняют possible origins; loops помечаются partial. Неподдержанные
numeric argument values сохраняются UNKNOWN, а не превращаются в string bindings.
Обработка control flow не доказывает достижимость, порядок runtime execution или
успешность вызова. Параметры и batch queues будут отдельным change.

Binding snapshots, placeholders и Java Value origins доступны отдельным adapter
[sql-lineage.md](sql-lineage.md); execution-only API сохраняет прежний coverage.
