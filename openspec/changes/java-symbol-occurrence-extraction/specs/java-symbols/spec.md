# Java symbols

## ADDED Requirements

### Requirement: Callable identity и параметры
#### Scenario: Overloads и constructors
- GIVEN constructors, метод с именем класса, m(int), m(String), array и varargs parameters.
- WHEN выполняется extraction.
- THEN callable IDs различны, constructor имеет имя <init>, dimensions/varargs представлены [], parameters типизированы.

#### Scenario: Body/comment edits
- GIVEN одинаковые signatures с изменённым body/comment/parameter name.
- WHEN сравниваются методы.
- THEN method ID сохраняется, source range обновляется.

#### Scenario: Generic signature
- GIVEN java.util.List<String> parameter и multidimensional array.
- WHEN строится UCM.
- THEN signature использует syntactic erasure, Parameter TypeRef сохраняет generic arguments.

#### Scenario: Duplicate identity
- GIVEN конфликтующие array/varargs signatures.
- WHEN выполняется extraction.
- THEN duplicate declaration отклоняется, не сливается.

### Requirement: Lexical declarations и references
#### Scenario: Parameter shadowing и receiver
- GIVEN field x, parameter x, this.x и other.x.
- WHEN строятся WRITE/READ occurrences.
- THEN bare x указывает parameter, this.x — field, other.x остаётся UNRESOLVED.

#### Scenario: Blocks и compound operations
- GIVEN field x и вложенный local x.
- WHEN выполняются increment/compound assignment и выход из block.
- THEN создаются READ+WRITE, local не протекает за пределы scope.

#### Scenario: Несколько классов
- GIVEN классы A/B с field x и методами чтения.
- WHEN разрешаются refs.
- THEN targets различаются как A.x и B.x.

#### Scenario: Visibility declaration
- GIVEN bare x до и после local declaration при наличии field x.
- WHEN разрешаются WRITE usages.
- THEN до declaration выбран field, после — local.

### Requirement: Неподтверждённые вызовы сохраняются
#### Scenario: Overloaded и неизвестный вызов
- GIVEN m(int)/m(String), m(1) и missing().
- WHEN собираются CALL occurrences.
- THEN m имеет AMBIGUOUS candidates без target, missing UNRESOLVED; CALLS edges отсутствуют.

### Requirement: Evidence, ranges и coverage
#### Scenario: Unicode declaration/use
- GIVEN Unicode names.
- WHEN entities проходят UcmBatch/EntityDocument roundtrip.
- THEN UTF-8 ranges точны, usages разрешены по lexical scope, DECLARES Relations содержат Evidence/PARTIAL Coverage.

#### Scenario: Неподдерживаемые scopes
- GIVEN lambda local shadow либо instanceof pattern shadow.
- WHEN выполняется extraction.
- THEN исключённое поддерево не создаёт ложной ссылки на field, coverage PARTIAL, внешние method declarations сохраняются.

#### Scenario: Parser diagnostic и provenance
- GIVEN syntax error либо SourceInput hash не соответствует bytes.
- WHEN вызывается extract.
- THEN syntax diagnostic возвращается явно; hash mismatch отклоняется.
- WHEN analyze_files получает parser diagnostic.
- THEN canonical indexing останавливается до публикации.

### Requirement: Подключение к incremental storage
#### Scenario: Callback contract
- GIVEN tuple captured Java files.
- WHEN вызывается analyze_files.
- THEN получены FileAnalysis для каждого файла с теми же entities, что extract.

#### Scenario: PostgreSQL lifecycle
- GIVEN два tracked Java files с overloaded methods и field write.
- WHEN incremental build, validation и publication выполняются.
- THEN symbols/scopes/occurrences/evidence сохранены; после body edit анализируется только изменённый файл, IDs методов стабильны, новый local разрешён.
- WHEN последующий source имеет parser error.
- THEN прежний published pointer сохранён.
