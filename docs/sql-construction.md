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
loops ограниченно моделируются и помечаются partial.

Число путей одного метода ограничено 256. При превышении анализ не отклоняется:
лишние пути отбрасываются, а все варианты, собранные по путям этого метода,
получают partial и причину `path limit reached: variants truncated` — включая
полные тексты, найденные до обрезки, потому что неполон сам набор вариантов.
Остаются первые пути в порядке обхода, поэтому SQL, который строится только в
отброшенных ветках поздних условий, в индекс не попадает. Отдельно найденные
строковые литералы от путей не зависят и причину не получают.

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

## Copy-on-write состояния Java SQL

Ветвление сохраняет прежний порядок обхода и лимит 256 путей. `_SqlFlow.clone`
разделяет граф variables/values до первой записи. Запись отделяет изменяемые
bindings/values с сохранением aliases, в том числе через saved scope; неизменяемые
fragments, reasons и spans остаются общими. При выходе из scope достаточно отделить
таблицу bindings: последующая запись values всё ещё проходит барьер.

Барьер записи покрывает declaration, assignment, dirty consumption и builder
operations, включая append внутри выражения. После вложенного вызова RHS ссылка
на binding обновляется: execution preview может отделить состояние. Это внутренний
протокол: код, который вручную меняет `_Variable`/`_Value`, сначала вызывает
`_writable()`. Legacy `_Flow` реализует этот hook как no-op. Поддержка builder
aliasing не расширяется: прежние partial reasons сохраняются. Фильтра по наличию
литералов и объединения эквивалентных путей нет.

Контролируемый замер, Linux/Python 3.12, по одному свежему процессу на режим;
одинаковый corpus и budget=256, полный digest фактов совпадает во всех режимах:

| Сценарий | Clone из main `d07a14d`, с | COW, с | RSS main → COW, МиБ | Материализаций main → COW |
| --- | ---: | ---: | ---: | ---: |
| 128 locals, 18 read-only branches | 1,997 | 0,180 | 79,07 → 53,93 | 3070 → 0 |
| 32 locals, 10 writing branches | 0,242 | 0,247 | 57,21 → 56,51 | 1022 → 1022 |

Read-heavy быстрее примерно в 11 раз; write-heavy в этом замере медленнее на 2,2%.
Это не SLA и не статистическая оценка эффекта на реальных репозиториях. Число
forks не уменьшено; метод по-прежнему может упираться в path budget. RSS включает
импорты и является process high-water, а не размером одного flow. Shared frames,
queries и choices всё ещё имеют стоимость копирования.

[Raw report](benchmarks/java-sql-flow-cow-2026-11-17.json) содержит SHA fixture,
исходников/стенда, digest всех entities, clone/materialization counts, CPU/RAM/cgroup,
RSS и process I/O blocks. Измеряется один текущий analyzer со сменой clone strategy:
main clone извлекается из фиксированного commit, исторический deepcopy служит
отдельным контрольным режимом. Это не сравнение полных старых checkout pipelines.

Воспроизведение (baseline commit должен присутствовать в Git object database):

```bash
uv run python -m code_crawler.java_sql_flow_benchmark --output /tmp/java-sql-flow.json
```
