# Решение

java.analyze возвращает ParseResult(symbols, diagnostics, source_sha256, byte_length, coverage). Input — immutable UTF-8 bytes. INVALID_UTF8 является diagnostic, а не silent replacement; symbols пуст. Tree-sitter Language загружается один раз, Parser создаётся на каждый вызов, чтобы concurrent parses не делили mutable parser.

Итеративный обход children (не только named_children) сохраняет ERROR и missing nodes; порядок стабилен по offsets/code/type. SourceSpan содержит start/end Position и byte offsets с exclusive end. Missing punctuation имеет нулевую длину. Symbol.source_span берётся прямо из AST; legacy start_line/end_line не меняются. Имена отсутствующих declarations не подменяются пустой строкой; корректные восстановленные symbols остаются доступными.

Indexer вызывает analyze и сохраняет diagnostics/hash/byte_length/parse_coverage в Java file attrs. Graph.failed остаётся отдельным каналом для IO/extraction исключений. CLI печатает path:line:byte_column, code и message; partial AST не срывает соседние файлы. Compatibility projection сохраняет эти attrs без отдельной миграции схемы. Старый legacy graph с прежней parser version должен быть обновлён index перед migrate-index, если comparison показывает отличие.

Legacy build сравнивает stat до/после read и пропускает нестабильный файл с явным failed diagnostic. UCM capture уже имеет own stable/secure IO checks. Source hash всегда относится к bytes, фактически переданным parser. Source drift после принятого capture относится к следующей индексации; глобального filesystem snapshot здесь нет.

COMPLETE означает только отсутствие parser diagnostics, а не полное semantic coverage. SQL construction/sink ranges не выдумываются из legacy line-only Query. Scope, overload identity и execution semantics не меняются. Baseline case отсутствующей syntax diagnostic заменён проверкой исправленного поведения.
