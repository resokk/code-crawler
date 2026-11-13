# Java parser diagnostics

`java.analyze(bytes)` возвращает ParseResult: symbols, diagnostics, source_sha256,
byte_length и coverage COMPLETE/PARTIAL. `java.parse(bytes)` сохраняет прежний
list[Symbol] API и использует тот же анализ. COMPLETE означает отсутствие parser
errors, а не полноту семантического анализа. Каждый вызов создаёт собственный
Tree-sitter Parser; immutable bytes не перечитываются из mutable файла.

Diagnostic содержит code SYNTAX_ERROR/MISSING_TOKEN/INVALID_UTF8, severity ERROR,
message, node_type и точный SourceSpan. Span содержит start/end Position
(строки с 1, UTF-8 byte columns с 0) и start_byte/end_byte; end исключающий.
Missing token имеет нулевую длину. Ошибки извлекаются из ERROR и missing nodes,
включая unnamed tokens, в детерминированном порядке. Некорректный UTF-8 не
подменяется replacement characters: возвращается diagnostic и пустой symbols.

Symbol дополнен source_span для диапазона декларации. Прежние line fields
сохраняются. SQL Query пока имеет только line: точные construction/sink ranges
появятся в отдельных changes. Синтаксически восстановленные декларации могут
быть извлечены из частичного AST; отсутствующие имена не превращаются в символы.

Indexer сохраняет diagnostics, hash bytes, byte_length и parse_coverage в attrs
Java file node. CLI сообщает path/координаты/code; файл с parser diagnostics не
отбрасывается, соседние файлы индексируются. Graph.failed остаётся для исключений
IO/extraction. Compatibility projection сохраняет file attrs вместе с errors;
миграция индекса старой parser version требует повторного index при несовпадении.
Проверка стабильности filesystem для UCM capture остаётся прежней; стандартный
legacy build проверяет stat до/после единственного read и сохраняет fingerprint
принятых bytes. При изменении файл пропускается с явным Graph.failed.
