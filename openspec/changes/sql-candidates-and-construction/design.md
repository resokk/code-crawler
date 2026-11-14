# Design

SQL_CANDIDATE envelope совместим с legacy; SqlConstruction и inline SqlVariant
задают owner, membership, ordered fragments и причины неполноты. Registry relations
CONSTRUCTS_SQL/HAS_SQL_CANDIDATE имеют Evidence и не означают execution.

JavaSqlAnalyzer переиспользует JavaCallAnalyzer и string helpers; scoped constants
устраняют collision между классами. Ветви исследуются независимо с пределом 32;
неподдержанные transforms/loops/aliasing явно partial. Profile изолирует reuse.

Миграция 0008 добавляет четыре normalized tables с deferred FK и fact guards.
Readiness restore использует тот же UcmBatch contract, что ingestion.
