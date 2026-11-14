# Design

SQLGlot token boundaries разделяют SQL без splitting strings/comments. Каждый
statement имеет original decoded slice и structured parse status/reasons. Parser
profile explicit postgres/mysql/tsql; SQLGlot version участвует в fingerprint.

Нормализованная копия AST используется для lexical scopes/CTE lookup; facts хранят
оригинальные identifier parts/text/quoted и dialect-normalized names. DML targets
и read operands отделены. Unknown/ambiguous column binding остаётся explicit;
без DB schema resolution не становится RESOLVED. Partial constructions не
порождают accesses на guessed placeholders.

Statement/access Entity types и registry relations замыкаются UcmBatch. Execution
links следуют только существующим construction origins, отдельно для sequential
statements и alternative variants. Evidence содержит Java origin и decoded
statement range, без ложного byte mapping.

Миграция 0010 использует normalized typed extensions/reasons/names, deferred FK
и immutable guards. Ingestion и readiness используют одинаковые Python invariants.
