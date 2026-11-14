# SQL candidates и construction

SQL discovery не является SQL execution. Новый opt-in Java SQL adapter расширяет
java.calls фактами SQL_CONSTRUCTION, SQL_CANDIDATE и типизированными variants/
fragments, не создавая EXECUTES_SQL и не утверждая data effects.

Константы Java разрешаются в lexical type scope: одноимённые поля классов не
перетирают друг друга, explicit A.FIELD использует одноимённый класс файла,
параметры/locals shadow unqualified field, this.FIELD не подменяется local.
Складываются только final fields (interface constants implicit final), доступные
в текущем файле. Внешние поля остаются dynamic, а не угадываются по basename.

Recovery переиспользует существующие Java string helpers: literals/text blocks,
concatenation, builders, String.join/format/formatted. Неизвестная часть имеет
DYNAMIC fragment __unknown__, static literal с таким текстом не становится dynamic.
Каждый fragment может иметь точный origin SourceRange; decoded text не считается
однозначным offset mapping к escaped Java literal. Условия дают отдельные варианты;
loops ограниченно моделируются и помечаются partial. При превышении path limit
анализ отклоняется, варианты не теряются молча.

SQL_CONSTRUCTION принадлежит owner Symbol и содержит nonempty variants.
SqlVariant содержит candidate_id, recovered text, partial/reasons и ordered
SqlFragment(kind STATIC/DYNAMIC, text, optional source_range). Join fragments
обязан совпадать с text; dynamic требует partial. SQL_CANDIDATE остаётся прежним
CodeEntity envelope для обратной совместимости; typed payload находится в
ucm_sql_variants, связывающей candidate и construction. Variants — возможные
строки, не доказательство достижимости или выполнения. CONSTRUCTS_SQL и
HAS_SQL_CANDIDATE Relations содержат Evidence/Resolution/Certainty/Coverage.

Старый legacy executes пока сохраняется для compatibility; новый canonical
adapter его не переносит. Execution sinks, SQL semantic AST, bindings и lineage —
отдельные changes. JDBC/Spring execution adapter описан в [sql-execution.md](sql-execution.md). Format flags, сложные side effects/aliasing и Java constructs
вне текущего coverage не считаются полным восстановлением. Partial содержит
явные причины. SQL-текст сохраняется даже без найденного sink.

## API и хранение

`java_sql.index_java_sql(conn, repository_id, root)` захватывает tracked bytes и
вызывает incremental indexing с JavaSqlAnalyzer. Profile `java.sql/1:` включает
Java call catalog fingerprint; смена профиля инвалидирует reuse. Результат —
BUILDING snapshot; readiness validation и publication вызываются отдельно.
Миграция 0008 хранит constructions, ordered variants/fragments/reasons в typed
таблицах; roundtrip через readiness gate проверяет весь UcmBatch.

Partial означает неполное или приближённое восстановление: после неизвестной
мутации builder сохранённый текст не обязательно равен итоговому SQL. Loops
рассматриваются в вариантах zero/one iteration; максимум 32 paths. Nested type
aliases доступны только в lexical scope; this.FIELD относится только к текущему
классу. Mutable builder fields не сворачиваются как constants. Поддержаны Java
Unicode/octal escapes и char concatenation. Integer literals нормализуются;
числовое сложение и floating conversion не угадываются. Неподдержанные format
flags/type conversions отмечаются partial.

SQL literals находятся и внутри expressions, чей итог не является SQL. JPQL
annotations/calls исключены; nativeQuery определяется AST flag, а не комментарием.
SQL semantic analysis должен учитывать kind fragments и partial reasons; оно,
bindings и lineage здесь не реализованы. Execution sinks доступны отдельным
opt-in `index_java_execution`; construction-only API сохраняет прежнее поведение.
