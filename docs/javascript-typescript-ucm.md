# JavaScript / TypeScript UCM adapters

`JavaScriptSourceAdapter` и `TypeScriptSourceAdapter` включены в стандартные
`index`, `index-sources` и `adapters list`. Descriptor/detector version — `1`;
prepared analysis version включает версии tree-sitter и обеих grammar packages.
Парсеры: `tree-sitter-javascript` для `.js/.jsx`, `tree-sitter-typescript`
для `.ts/.tsx` (отдельная TSX grammar). Producer работает только с captured bytes,
в worker thread; не исполняет код, не читает ambient files, не обращается к сети/БД.

## Normative model и совместимость

Используется существующий UCM contract без новых EntityType/RelationKind и миграций.

| Конструкция | Canonical facts |
| --- | --- |
| Класс, interface, type alias, enum | `Symbol(CLASS)`; исходный синтаксис различим через source Evidence/ranges |
| Функция, метод, arrow/function expression | `Symbol(METHOD)` и `CallableSignature` |
| Переменная, параметр, поле | `LOCAL_VARIABLE`, `PARAMETER`, `FIELD` |
| Файл, тип, callable, блок, catch/for | `Scope(FILE/TYPE/CALLABLE/BLOCK)` и `CONTAINS` между scopes |
| Объявление, использование типа/имени, вызов | `Occurrence(DECLARATION/REFERENCE/CALL)` и `DECLARES/REFERENCES` с Evidence |
| Лексический вызов внутри callable | `CALLS` от owner symbol; неизвестная цель — `UNRESOLVED` с reason |
| Отсутствующий импорт, dynamic import | `ExternalReference(SymbolSelector)` с deferred reason |
| Поддержанный HTTP-клиент | `ExternalReference(HttpSelector)` и `EXTERNAL_DEPENDENCY` |

Ключи repository-local: path + declaration byte offset; callable_key включает
owner declaration site, имя и упорядоченные parameter types. Поэтому одинаковые
перегрузки, overload signatures и implementation не сливаются. Одинаковый captured
input даёт одинаковые IDs и content независимо от full/incremental запуска.
Все координаты — 1-based line / 0-based UTF-8 byte column. `TypeRef` сохраняет
аннотацию/параметры generics текстом; type identifier occurrences могут получить
локальную цель. Generic inference и реализация interface не утверждаются.
Body-free overload/interface signatures никогда не служат runtime CALLS target.

## Импорты и локальное разрешение

Поддержаны static default/named/namespace imports, aliases, export declarations,
`export default localName`, named reexports, export-star chains и reexport
импортированных aliases. Named exports сохраняются в подготовленном каталоге;
импорты дают references на конкретные symbols с Evidence. Циклы обрабатываются
ограниченным fixed-point проходом. Конфликтующие star exports не выбирают случайную
цель. Только единственная найденная implementation даёт RESOLVED CALLS.

Relative paths разрешаются в captured inventory своего адаптера: explicit file,
последовательно `.ts/.tsx/.js/.jsx/.d.ts`, затем `index` с этими suffixes.
TS imports с `.js/.jsx` проверяют `.ts/.tsx/.d.ts` перед исходным suffix.
Path traversal за repository root не допускается. Отсутствующие пути-кандидаты
тоже записываются как dependencies: добавление ранее отсутствующего модуля,
изменение/удаление модуля и транзитивный reexport инвалидируют потребителей.

`import type`, inline `type` specifiers и type reexports дают type references,
но не definite runtime CALLS. Учитываются lexical scopes, параметры, destructuring,
затенение, `var` function scope и явные записи в callable bindings. Namespace
member calls разрешаются только через соответствующий static namespace import.
Произвольные object methods, dynamic dispatch и computed calls остаются unresolved.
`import(expression)` сохраняется как deferred selector, включая literal paths:
этот профиль не объявляет dynamic import статическим runtime binding.

Через `prepare_inventory` оба адаптера строят локальный JS/TS-каталог из immutable
captured inputs. Межъязыковая ссылка разрешается только если оба языка зарегистрированы
и target facts действительно будут выданы его адаптером. Зависимости проходят между
adapter scopes; изменение JS-модуля инвалидирует импортирующий TS и наоборот.

Package.json
exports, node_modules, CommonJS require/module.exports, custom module loaders,
полноценный TypeScript type checker не поддержаны.
Неизвестный package сохраняет deferred selector без запроса удалённого репозитория.

## TS project configuration и incremental

Standalone TS adapter по умолчанию владеет `.json` route. В CLI маршрут принадлежит
OpenAPI; TS создаётся с `include_json=False`, а `tsconfig.json` получает через
captured inventory независимо от language. Зависимости от config сохраняются.
Прочие JSON без OpenAPI root/ref — metadata-only `SOURCE_ANALYSIS` с UNSUPPORTED coverage;
JSON не разбирается как TypeScript. Поддержан strict JSON `tsconfig.json`:
`compilerOptions.baseUrl`, `compilerOptions.paths`, exact/one-wildcard aliases;
выбирается ближайший ancestor config. Candidates остаются внутри repository root.

JSONC, `extends`, project `references` и другие moduleResolution modes не
интерпретируются; неподдержанный/невалидный config имеет diagnostic
`TS_CONFIG_UNSUPPORTED`, его aliases не применяются. Relative imports продолжают
работать. Положительные и отрицательные ancestor tsconfig dependencies позволяют
переразрешить импорт при изменении, добавлении и удалении config. При отсутствии
изменений SOURCE_ANALYSIS и факты переиспользуются. Изменение descriptor/parser
version инвалидирует соответствующие adapter scopes через существующий registry.

## HTTP и неопределённость

Поддержаны незатенённый global `fetch(url, {method: "POST"})` (default GET),
а также `client.get/post/put/patch/delete/head/options(url)` для default/namespace
ES import из `axios`. Известные string URL дают method/path/service; query и
fragment не входят в `HttpSelector.path`. Template substitutions в path заменяются
на `{dynamic}`, исходное выражение сохраняется в Evidence, reason отмечает dynamic
portions. Remote resolution всегда UNRESOLVED, coverage PARTIAL.

Неизвестный HTTP method, произвольный URL expression, динамический host,
spread/computed options, axios instances/request/config-object calls и обёртки
не угадываются. Обычный CALL occurrence остаётся доступным, но HTTP selector
без достаточных данных не создаётся. Escaped string literals не вычисляются.

## Coverage и ошибки

Все три capabilities (`<language>.symbols`, `.references`, `.http`) — PARTIAL:
это ограниченный syntax-only профиль без runtime/data-flow guarantees. Семантические
ошибки языка вне tree-sitter grammar (например дублирование lexical declaration)
не заменяют TypeScript compiler diagnostics. Anonymous callables имеют собственный Symbol с именем `<anonymous@byte>` и scope;
их CALLS принадлежат callback, а не внешней функции. Named function expressions
сохраняют локальное self-binding для рекурсивных вызовов.

Syntax error даёт `SYNTAX_ERROR` с byte range и metadata-only analysis этого файла;
остальные файлы остаются индексируемыми. Бюджет source — 4 MB / 100000 named AST
nodes; превышение даёт `SOURCE_LIMIT` / `AST_LIMIT` без semantic facts. Неожиданное
исключение producer/validation проходит через AdapterError и не публикует snapshot.

Тесты: `tests/test_javascript_adapter.py` (положительные и отрицательные случаи,
UcmBatch closure, Unicode, JSX/TSX, HTTP, перегрузки, затенение),
`tests/integration/test_javascript_storage.py` (PostgreSQL 15 publication, Evidence,
SOURCE_ANALYSIS, no-change reuse, config invalidation, full/incremental equality,
adapter fingerprint invalidation и сохранение Java facts).
