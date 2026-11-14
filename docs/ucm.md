# UCM Entity Contract v1

Первый контракт UCM вводится независимо от legacy-хранилища и анализаторов.
Модуль `code_crawler.ucm` определяет Entity Envelope и SourceFile.
Нормативные поля типизированы; произвольного JSONB-контейнера нет.

EntityType v1: SOURCE_FILE, CLASS, METHOD, SQL_CANDIDATE, SQL_CONSTRUCTION, SYMBOL, SCOPE,
OCCURRENCE, OPERATION, VALUE, RELATION, EXTERNAL_REFERENCE. Модели описаны ниже.
Конвертеры появятся отдельными changes.
SQL_CANDIDATE означает обнаруженный SQL и не доказывает его выполнение.

Каждая сущность содержит contract_version=1, repository_id, logical_key,
entity_type, id и name. SourceFile дополнительно содержит относительный POSIX path,
language и SHA-256 исходных bytes (64 lowercase hex). Абсолютные пути, пустые
сегменты, '.', '..', backslash, drive prefixes и NUL запрещены.

ID вычисляется как SHA-256 канонического JSON-массива
["ucm", 1, repository_id, entity_type, logical_key], UTF-8, ensure_ascii=False,
separators=(',', ':'); префикс результата — ucm:. Snapshot и содержимое не входят
в logical ID. repository_id — явный непрозрачный идентификатор, не basename.
Для SourceFile logical_key равен path. Для остальных сущностей ключ определяет
адаптер; для callable Symbol ключ нормативно определяется сигнатурой.

SourceRange содержит source_file_id, start и end. Position использует строки с 1
и UTF-8 byte columns с 0; end исключающий. Пустые диапазоны допустимы; end раньше
start запрещён. Неизвестные координаты представлены отсутствием source_range,
а не вымышленными значениями. Проверка границ реального файла и существования
source_file_id относится к batch validation будущего change.

Модели immutable, неизвестные поля и неявное преобразование строк в числа
запрещены. Сериализация: model_dump_json(), загрузка: model_validate_json().
Дискриминированный EntityDocument экспортирует JSON Schema через
entity_json_schema(); schema хранится в docs/ucm-entity.schema.json.
Schema проверяет структуру; вычисляемый ID и порядок координат дополнительно
проверяет Python validator. Изменение этих правил требует версии контракта.

## Symbol model

Добавлены EntityType SYMBOL, SCOPE, OCCURRENCE без изменения существующих
CLASS/METHOD документов. Symbol — детальная модель декларации, symbol_kind:
CLASS, METHOD, CONSTRUCTOR, FIELD, PARAMETER, LOCAL_VARIABLE. qualified_name —
имя для поиска; identity определяется logical_key, а не только этим именем.

TypeRef содержит непустое name, resolution UNRESOLVED/RESOLVED/AMBIGUOUS и
необязательный target_symbol_id. Только RESOLVED требует target; остальные
запрещают его. Имя хранит каноническое написание адаптера, включая массивы и
параметры типов; это ссылка на тип, а не результат глобального резолвинга.

CallableSignature содержит упорядоченный tuple parameter_types и необязательный
return_type. callable_key(owner_key, name, signature) кодирует JSON-массив
["callable", owner_key, name, [parameter type names]]. Return type, имена
параметров, позиции и resolution не меняют overload identity. Адаптер обязан
канонизировать имена типов согласно языку; helper сам типы не разрешает.
Для METHOD/CONSTRUCTOR обязательны owner_key и signature; logical_key обязан
совпадать с callable_key. Для других symbol_kind signature и owner_key запрещены.
Это не меняет legacy qualified_name: его неоднозначности исправит Java adapter.

Scope задаёт scope_kind FILE/TYPE/CALLABLE/BLOCK, parent_scope_id и
owner_symbol_id (необязательные), а Symbol может указывать scope_id и type_ref.
Occurrence задаёт occurrence_kind DECLARATION/REFERENCE/READ/WRITE/CALL,
обязательные scope_id и source_range, resolution и target_symbol_id с теми же
правилами, что TypeRef. Неразрешённые occurrences сохраняются.
Идентичность scope и occurrence задаёт адаптер в logical_key; проверка
существования ссылок, вложенности диапазонов и циклов — будущая batch validation.

## Operation / Value и минимальный Data Flow

EntityType OPERATION и VALUE расширяют реестр. Operation содержит scope_id,
operation_kind READ/ASSIGN/CALL/RETURN/CONCAT, упорядоченные input_value_ids и
output_value_ids (tuple). Позиция входа — позиция операнда/аргумента; повторы
входов допустимы. Выходы уникальны, один ID не может быть одновременно входом
и выходом: значения представляют отдельные определения, не изменяемые переменные.
ASSIGN имеет один вход и один выход, READ — ноль входов и один выход,
CONCAT — минимум два входа и один выход, RETURN — ноль или один вход без выходов.
CALL допускает любое число входов и максимум один выход; только CALL может
содержать callee: TypeRef (используется тот же контракт разрешения символа).
Отсутствие callee означает неизвестную цель вызова.

Value содержит value_kind LITERAL/SYMBOLIC/UNKNOWN, необязательный type_ref,
partial и literal (str/int/finite float/bool/null). LITERAL допускает null и
пустую строку, partial=false; SYMBOLIC не содержит literal; UNKNOWN не содержит
literal и требует partial=true. SYMBOLIC может быть partial, например результат
конкатенации с неизвестным фрагментом. Никакое значение не вычисляется запуском
анализируемого кода. SQL-текст в Value не доказывает SQL execution.

Минимальный поток задаётся Operation.inputs → Operation → Operation.outputs;
цепочка связывается общими Value ID. Типизированные Relations/Evidence
описаны ниже. Контракт не реализует SSA/CFG, анализ алиасов, ветвей и heap.
Ключи операций и значений задаёт адаптер; проверка существования ссылок,
принадлежности scope/repository, единственного producer и распространение
partial требуют последующего batch validator/анализатора. Здесь проверяются
локальная структура и кардинальности, без предположений о полном графе.

## Relations, Evidence, Resolution, Certainty, Coverage

EntityType расширяется RELATION. Relation содержит source: EntityRef,
relation_kind, resolution: Resolution, certainty: Certainty, непустой tuple
Evidence и Coverage. EntityRef содержит id и entity_type; Resolution задаёт
второй конец связи либо сохраняет кандидатов без подтверждённого target.

Resolution.status: RESOLVED (обязательный target, candidates пуст), UNRESOLVED
(нет target/candidates), AMBIGUOUS (не менее двух уникальных candidates, нет
target), PARTIAL (не менее одного candidate, нет target). Нерешённые статусы
требуют reason. Кандидаты не считаются подтверждёнными рёбрами. Это новый
контракт отношений; прежние TypeRef/Occurrence.resolution остаются совместимыми.

Реестр RelationKind задаёт допустимые пары EntityType:

| Kind | Source | Target/candidate |
| --- | --- | --- |
| CONTAINS | SOURCE_FILE, CLASS, SYMBOL, SCOPE | CLASS, METHOD, SYMBOL, SCOPE, OPERATION |
| DECLARES | OCCURRENCE | CLASS, METHOD, SYMBOL |
| REFERENCES | OCCURRENCE | CLASS, METHOD, SYMBOL |
| CALLS | METHOD, SYMBOL, OPERATION | METHOD, SYMBOL |
| CONSUMES | OPERATION | VALUE |
| PRODUCES | OPERATION | VALUE |
| FLOWS_TO | VALUE | VALUE |
| EXTERNAL_DEPENDENCY | SYMBOL, METHOD, OCCURRENCE, OPERATION, VALUE | EXTERNAL_REFERENCE |

Реестр immutable и экспортируется relation_registry(). Проверяются все
кандидаты, даже когда разрешённого target нет. Подтипы SYMBOL и OPERATION
дополнительно проверяются validate_relation_endpoints(): CALLS требует
METHOD/CONSTRUCTOR символы либо CALL operation, DECLARES — DECLARATION
occurrence. Эта функция принимает каталог реальных сущностей и проверяет
наличие source/target/candidates, совпадение заявленных типов и repository_id.
Отношения остаются локальными; внешние зависимости представлены локальным
ExternalReference (см. ниже).
Рекурсивные CALLS допустимы, циклы CONTAINS здесь не проверяются.

Evidence содержит source_range, analyzer, analyzer_version, rule и description;
это воспроизводимое статическое обоснование, не свидетельство runtime execution.
Evidence вкладывается в Relation, отдельного ID пока нет. Certainty:
STATIC_PROVEN, INFERRED, UNKNOWN. STATIC_PROVEN допустим только для RESOLVED;
RESOLVED сам по себе не повышает certainty. Coverage содержит capability,
analyzer_version, status COMPLETE/PARTIAL/UNSUPPORTED и tuple reasons.
PARTIAL/UNSUPPORTED требуют непустые reasons, COMPLETE запрещает их.
UNSUPPORTED допускает только UNRESOLVED с UNKNOWN certainty. Coverage относится
к заявленной capability и не означает полноту анализа всего репозитория.

Каждый relation document проверяется Python и сериализуется EntityDocument.
JSON Schema выражает структуру; межполевые условия и реальные endpoints
проверяются Python. Id отношения задаётся прежним logical_id по adapter key;
разрешение и evidence могут изменяться без изменения logical identity.
Evidence ranges должны ссылаться на реальный SourceFile того же repository при
validate_relation_endpoints(). Проверка границ ranges, истинности evidence и
полноты coverage требует анализатора и последующего batch validation.

## ExternalReference

EXTERNAL_REFERENCE — локальная сущность зависимости, а не ссылка на сущность
другого проиндексированного репозитория. source: EntityRef указывает на локальный
SYMBOL/METHOD/OCCURRENCE/OPERATION/VALUE. selector — дискриминированный контракт:

- SYMBOL: qualified_name, parameter_type_names (tuple либо null, где null —
  неизвестная сигнатура, пустой tuple — известные ноль параметров).
- HTTP: method (uppercase GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS/TRACE/CONNECT),
  path (начинается с '/', без query/fragment), optional service.
- DATABASE: connection (логический alias без credentials), optional schema_name,
  table. Регистр имён сохраняется, канонизация/quoted semantics — задача адаптера.

Это минимальный реестр selectors; BPMN, datasets и прочие расширят его в своих
adapter changes. Selector не содержит foreign entity IDs. repository_hint и
version_hint — optional непрозрачные подсказки, не доказательство совпадения.

Обязательны reason, evidence (непустой tuple), certainty и coverage; resolution
фиксирован UNRESOLVED, resolved target и candidates отсутствуют. Certainty
относится к обнаружению зависимости, не к разрешению цели. UNSUPPORTED coverage
требует UNKNOWN certainty. Selector и hints сохраняются без сети и обращения к
другим индексам. Результат query-time resolver будет отдельным объектом и не
изменит опубликованный ExternalReference.

validate_external_reference проверяет локальный source, его тип/repository и
source files evidence по переданному каталогу. RelationKind.EXTERNAL_DEPENDENCY
допускает те же source types → EXTERNAL_REFERENCE. RESOLVED такой Relation
означает только установленную локальную связь с ExternalReference, а не
разрешённую внешнюю цель; CALLS → EXTERNAL_REFERENCE запрещён.

Logical key задаётся адаптером (например, стабильный ключ occurrence); selector,
hints, evidence не входят автоматически в ID. Отдельные callsites могут иметь
одинаковый selector и разные ID. Совпадение selector не создаёт глобальную связь.

## SQL construction

SqlConstruction принадлежит Symbol (CLASS/METHOD/CONSTRUCTOR) и содержит
непустые SqlVariant: candidate_id, text, partial, partial_reasons и ordered
SqlFragment (STATIC/DYNAMIC, text, optional SourceRange). Конкатенация fragments
равна text; dynamic требует partial и причины. Candidate IDs уникальны внутри
construction и не принадлежат нескольким constructions в одном batch.
CONSTRUCTS_SQL связывает SYMBOL → SQL_CONSTRUCTION, HAS_SQL_CANDIDATE —
SQL_CONSTRUCTION → SQL_CANDIDATE; batch проверяет owner и membership.
Обнаружение не доказывает execution. Подробнее: [sql-construction.md](sql-construction.md).
