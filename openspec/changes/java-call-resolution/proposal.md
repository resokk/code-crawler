# Java call resolution

## Проблема и цель

CALL occurrences пока сохраняют только имя и возможные overloads. Нужен проверяемый локальный declared-method graph между Java файлами и сохранение неизвестных/внешних целей без глобального linking.

## Границы

Закрытый repository catalog, conservative receiver/argument applicability, CALLS и согласованные occurrences, ExternalReferences, Evidence/Coverage, интеграция с UCM incremental/publication. Без classpath/compiler equivalence, inheritance graph, runtime dispatch, SQL execution и переключения legacy CLI.
