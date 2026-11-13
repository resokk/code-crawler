# Java parser diagnostics

## ADDED Requirements

### Requirement: Точные координаты и provenance
#### Scenario: Корректный Unicode/CRLF source
- GIVEN UTF-8 Java с Unicode identifier и CRLF.
- WHEN java.analyze выполняется.
- THEN diagnostics пусты, coverage COMPLETE, SHA-256/byte_length соответствуют bytes, declaration spans выделяют точные class/method bytes и используют byte columns.
- AND java.parse возвращает прежний список symbols.

### Requirement: Syntax diagnostics без silent recovery
#### Scenario: Отсутствующий unnamed token
- GIVEN пропущенная точка с запятой.
- WHEN анализируется AST.
- THEN MISSING_TOKEN указывает zero-width range отсутствующей punctuation.

#### Scenario: ERROR после Unicode
- GIVEN некорректное выражение после UTF-8 строки.
- WHEN анализ повторяется.
- THEN SYNTAX_ERROR и byte range точны, coverage PARTIAL, результаты детерминированы.

#### Scenario: Невалидный UTF-8
- GIVEN bytes с некорректной последовательностью после CRLF.
- WHEN выполняется analyze.
- THEN INVALID_UTF8 содержит точные offsets/line/column, symbols пусты, replacement characters не используются.

#### Scenario: Recovered declarations
- GIVEN malformed class/method/field и отсутствующие имена.
- WHEN выполняется extraction.
- THEN diagnostics сохранены, пустые имена symbols не создаются, extraction не падает для проверенных recovery cases.

### Requirement: Изоляция источников
#### Scenario: Concurrent parses
- GIVEN 24 разных immutable sources.
- WHEN они анализируются в worker pool.
- THEN имена, fingerprints и diagnostics каждого результата соответствуют своему input.

#### Scenario: Mutable buffer
- GIVEN bytearray input.
- WHEN вызывается analyze.
- THEN input отклоняется, а не используется как mutable source.

#### Scenario: File drift во время чтения
- GIVEN файл изменяется между read и stat verification.
- WHEN строится legacy graph.
- THEN файл исключён с source changed diagnostic в failed, соседний файл индексируется.

### Requirement: Diagnostics доходят до пользователя и storage
#### Scenario: Соседние Java файлы
- GIVEN broken и valid Java файлы.
- WHEN строится graph.
- THEN broken file содержит structured diagnostics/hash/PARTIAL, valid method сохранён, parser recovery не попадает в Graph.failed.

#### Scenario: Реальный CLI и PostgreSQL
- GIVEN tracked Java с missing token либо invalid UTF-8 и соседний valid file.
- WHEN CLI index выполняется отдельным процессом.
- THEN exit 0, stdout содержит path/line/code, file attrs в PostgreSQL сохраняют exact hash/diagnostics/PARTIAL, valid method доступен.
