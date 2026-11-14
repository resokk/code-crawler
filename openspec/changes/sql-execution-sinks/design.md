# Design

JavaExecutionAnalyzer расширяет JavaSqlAnalyzer отдельным scoped flow pass.
Typed receiver + method/argument shape определяют sink; имя метода само по себе
недостаточно. prepare* сохраняет snapshot SQL value, execute* создаёт execution;
local symbol IDs различают scopes/aliases. Перезапись, close и escape удаляют
origin. Ветви клонируют environment; unsupported flow не получает definite SQL.
String preview выполняется на clone, чтобы не повторять builder mutations.

SqlExecute ссылается на callable owner и CALL operation с ordered argument Values.
EXECUTES_SQL подтверждает site; USES_SQL_CONSTRUCTION хранит resolved/partial/
unresolved construction origin. Evidence сохраняет invocation и preparation range.
Нет EXECUTES_STATEMENT или утверждений о data effects до SQL semantic analysis.

Миграция 0009 вводит extension и registry seeds, deferred FK и immutable guards.
Ingestion и readiness проверяют API/callee, callable scope и bounds аргумента.
Analysis profile включает предыдущие fingerprints и изолирует reuse.
