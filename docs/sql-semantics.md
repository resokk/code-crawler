# SQL semantic access analysis

Новый opt-in semantic adapter расширяет execution/construction граф отдельными
SQL_STATEMENT и DATA_ACCESS facts. SQLGlot AST разбирается по statements:
эффекты соседних statements не смешиваются. Оригинальный SQL и позиции в decoded
candidate text сохраняются отдельно от Java SourceRange (прямой mapping не заявлен).

Профили dialect — postgres (default), mysql, tsql; автодетекции нет. Identifier
содержит исходные text/quoted и normalized name согласно dialect. Catalog/schema/
table/column parts хранятся раздельно. Имена объектов без schema catalog остаются
UNRESOLVED: syntactic binding к table alias не доказывает существования DB object.
Колонки multi-source без qualifier, derived outputs, stars и неизвестные имена
сохраняются явно, без угадывания по одному basename.

SELECT/set operations, INSERT/UPDATE/DELETE, MERGE, UPSERT и основные table DDL
дают отдельные table/column accesses READ/INSERT/UPDATE/DELETE/MERGE/DDL. CTE и
subquery aliases не становятся физическими таблицами; исходные physical tables
сохраняются. Unsupported syntax и parse errors сохраняют statement с diagnostic
reasons. Partial/dynamic constructions не анализируются как достоверный SQL AST.

HAS_SQL_STATEMENT связывает candidate → statement; effect relations связывают
statement → DATA_ACCESS и содержат Evidence/Certainty/Coverage. Execution sites
получают EXECUTES_STATEMENT только через существующую construction resolution;
неиспользуемый SQL остаётся statement без execution. Runtime execution, actual
DB effects, connection identity и bindings этим анализом не доказываются.

## API, хранение и границы

`sql_semantic.analyze_statements(text, dialect="postgres")` возвращает ordered
StatementAnalysis с typed SqlAccessDetail. SQLGlot token boundaries учитывают
semicolon внутри strings/comments/dollar quotes. Parse error одного statement
не удаляет остальные. Ошибка tokenization сохраняет весь text одним ERROR.

`java_semantic.index_java_semantic(conn, repository_id, root, dialect="postgres")`
строит BUILDING snapshot; validate_snapshot и publish_snapshot вызываются отдельно.
Profile `java.sql.semantic/1:` включает dialect, SQLGlot version и предыдущие
execution/construction/catalog fingerprints; смена profile инвалидирует reuse.
Неизменённые semantic facts переносятся вместе с file ownership.

Миграция 0010 хранит statements, ordered diagnostic reasons, accesses и identifier
parts в normalized typed tables с deferred FK и immutable guards. Gate проверяет
candidate slice/position, effect relation/owner и execution construction origin.
Один candidate может иметь несколько sequential statements: каждый имеет собственную
execution relation. Alternative variants дают PARTIAL candidates, failed/partial
statements не становятся definite execution targets. SQL без sink всё равно
сохраняется с semantic facts.

SELECT/UNION, lexical CTE/subqueries, correlated qualifiers, UPDATE FROM, tuple
assignment, INSERT SELECT, ON CONFLICT/ON DUPLICATE, MERGE actions, DELETE USING,
CREATE/ALTER/DROP/TRUNCATE TABLE/VIEW/INDEX поддерживаются в текущем AST coverage.
CREATE TABLE AS QUERY сохраняет DDL и INSERT target; ALTER column definition/drop
не превращается в чтение data column.
Derived output aliases и star expansion не угадываются; projection/binding lineage —
следующий этап. MySQL multi-target DELETE сохраняется как ERROR с explicit reason;
non-table DDL/commands — UNSUPPORTED. Table-valued expressions дают PARTIAL coverage.
DDL constraint/index expressions и triggers/cascades не объявляются исчерпывающим
списком actual DB effects. SQLGlot AST success не является server-side validation.
Legacy `sql.analyze` остаётся совместимым агрегированным PostgreSQL projection;
новые canonical facts используют существующие operation/clause helpers, не меняя
legacy identity или CLI writer.
