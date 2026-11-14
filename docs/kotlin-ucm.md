# Kotlin UCM adapter v1

`KotlinSourceAdapter` активирован в CLI для `.kt` и `.kts`. Tree-sitter Kotlin
1.1.0 разбирает только captured bytes в worker thread; исходники не исполняются,
файлы, classpath и внешние сервисы адаптер не читает. Лимиты: 2 MB на файл,
100 000 AST nodes и глубина 150. Ошибки UTF-8, parser recovery и превышение
лимитов дают SourceAnalysis diagnostics, без семантических facts этого файла.
Все возможности объявлены PARTIAL; `.kts` дополнительно получает
`kotlin.SCRIPT_PARTIAL`: host bindings и implicit receivers неизвестны.

## Символы и идентичность

Пакет и explicit imports/aliases формируют lexical context. Файлы, типы,
callables и blocks получают Scope; классы, интерфейсы и objects используют
существующий Symbol CLASS; отдельный symbol_kind для interface/object не вводится.
Функции — METHOD, constructors — CONSTRUCTOR с именем `<init>`, свойства —
FIELD/LOCAL_VARIABLE, параметры — PARAMETER. Новых enum/storage типов нет.
Объявления и поддержанные lexical reads/writes имеют Occurrence и Evidence.
Ranges используют captured SourceFile ID, строки с 1 и UTF-8 byte columns с 0.

Callable identity использует canonical `callable_key`: owner + name + ordered
parameter types. Nullable и generic syntax сохраняется без erasure. Extension
receiver входит в owner key как `:receiver:<type>`; поэтому обычная функция и
extension, а также extensions разных receiver types имеют разные IDs.
Return type не является discriminator перегрузки. Top-level owner содержит
source path; перенос функции в другой файл меняет ID.

## Разрешение вызовов

Разрешаются только уникальные repository-local signatures при точном совпадении
известных типов аргументов. Поддержаны Int/String/Boolean literals и явно
типизированные lexical variables/parameters этих builtin типов. Пользовательские
типы аргументов/receivers остаются deferred. Обнаруженные одноимённые пользовательские
классы и explicit imports, затеняющие builtin, запрещают такое разрешение. Extension требует известный
совпадающий builtin Int/String/Boolean receiver, видимость через пакет/explicit import. Nullable/generic
applicability, default/vararg argument expansion, inferred generic signatures,
open/override dispatch, private/protected callables и compiler-generated members
не разрешаются. Аргументы по имени и safe calls остаются deferred.

Java interoperability ограничен explicit `public static` methods и explicit
qualified/imported class receiver без lexical shadowing. Используются те же
canonical Symbol IDs, что Java symbols producer. Instance/virtual methods,
Java overload widening/boxing, static-import calls и compiler classpath
не поддержаны. Java producer должен быть активирован в registry; Kotlin не
публикует копии Java symbols. Ошибочный Java файл не участвует в каталоге.

Неизвестные/неоднозначные calls сохраняют UNRESOLVED Occurrence и discoverable
ExternalReference с SymbolSelector, reason и Evidence. CALLS создаётся только
для доказанной локальной цели с callable owner; remote targets не ищутся.
Это bounded lexical analysis, а не проверка компиляции Kotlin.

## SQL

Распознаются explicit receiver types/import aliases:

- `java.sql.Connection.prepareStatement/prepareCall`: construction без execution;
- `java.sql.Statement.execute/executeQuery/executeUpdate`;
- `org.springframework.jdbc.core.JdbcTemplate.query/queryForObject/queryForList/update/execute`.

Первый аргумент SQL должен быть string/raw literal, concatenation таких строк
или цепочка immutable local `val`. Глубина вычисления ограничена 30; циклы,
mutable vars, поля/getters, templates, builders, trimIndent, arbitrary calls и
control-flow joins не вычисляются. Неизвестный аргумент даёт `kotlin.SQL_DYNAMIC`,
без выдуманного static SQL. Литералы декодируются без исполнения.

Создаются canonical SQL_CANDIDATE/SqlConstruction и Evidence relations;
execution создаёт Operation, Value и SqlExecute с USES_SQL_CONSTRUCTION.
Общий SQL semantic analyzer извлекает PostgreSQL SqlStatement/DataAccess;
EXECUTES_STATEMENT связывает execution со statement. Ошибки SQL parser отражаются
в SourceAnalysis как `sql.CANDIDATE_PARSE_ERROR`.
PreparedStatement lifecycle, parameter binding, dialect selection, connection/schema
resolution и SQL parameter lineage в v1 не поддержаны.

## Registry и incremental

Опциональный `prepare_inventory(assigned, inventory)` расширяет prepare контракт:
registry передаёт immutable captured inventory, включая другие языки. Старые
адаптеры продолжают использовать prepare(assigned). Inventory не даёт DB/root.

Kotlin analysis_version включает detector/parser version и sorted path/hash
manifest Kotlin/Java. Поэтому изменение/добавление/удаление потенциальной цели,
включая ранее отсутствующую или ambiguous, консервативно инвалидирует весь Kotlin
scope. FileAnalysis также сохраняет известные Kotlin/Java file dependencies.
Изменение descriptor/fingerprint инвалидируется обычным per-adapter planner;
без изменений SourceAnalysis и facts переносятся. Это намеренно консервативнее
точечных symbol dependencies. Java scope от изменений Kotlin не инвалидируется.

Публикация использует общий staging/validation/atomic publication lifecycle;
адаптер не пишет в БД и не создаёт второй граф.
