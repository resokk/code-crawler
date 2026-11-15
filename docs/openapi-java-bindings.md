# OpenAPI → Java bindings (D06)

Canonical Java и OpenAPI adapters совместно строят локальные Spring MVC/WebFlux
bindings. Java AST, Call Graph и SQL analyzers переиспользуются; HTTP adapter не
исполняет Java, expressions, HTTP или SQL и не читает другие repositories.

```bash
uv run code-crawler index /repo --repository-key org/repo
uv run code-crawler index-sources /repo --repository-key org/repo \
  --java-profile execution --publish
```

Default CLI registry включает OpenAPI adapter и Java adapter внутри Kafka wrapper;
wrapper передаёт оба immutable Java catalogs. Programmatic API:
`AdapterRegistry((JavaSourceAdapter(profile="execution"), OpenApiSourceAdapter()))`.
Без Java adapter OpenAPI сохраняет schema-only поведение D05; capability bindings
UNSUPPORTED. В CLI Java catalog существует и при отсутствии Java files, поэтому
операции без implementation получают unresolved handler и deferred selector.
Feign facts сохраняются даже без OpenAPI документа.

## Typed facts и версии

Миграция `0029_openapi_java_bindings.sql` расширяет существующий relation registry,
без нового графа или subtype tables:

| Relation | Смысл |
| --- | --- |
| `HTTP_ATTRIBUTE` | Java Method → Value: kind, path, methods, media, conditions, service |
| `HTTP_REQUEST_DTO`, `HTTP_RESPONSE_DTO` | Java Method → declared Java DTO class types |
| `OPENAPI_HANDLER` | OpenAPI operation → canonical Java handler Method |
| `OPENAPI_REQUEST_DTO`, `OPENAPI_RESPONSE_DTO` | contract schema → signature-derived Java DTO candidates |
| `OPENAPI_JAVA_PARAMETER` | contract parameter/alias → annotated Java Parameter |

Исходные paths и имена placeholders остаются в D05 facts и Java HTTP attributes.
Handler relation содержит Evidence из OpenAPI, Java class/method mapping и, при
наличии, application context configuration. Canonical Java Symbol IDs не
пересоздаются. Request/response DTO и parameter binding не выводятся по совпадению
имён schema/class. Конфликт имён не скрывается выбором первого файла.

Versions: Java adapter descriptor `2`, Java HTTP analyzer/catalog `java.http/1`,
CLI Kafka wrapper сохраняет собственный version prefix перед Java descriptor `2`.
OpenAPI adapter `openapi/2`, schema analyzer `openapi/1`, binding capability
`openapi.java/1`. HTTP/binding Coverage всегда PARTIAL; RESOLVED означает unique
совместимую статическую декларацию, с INFERRED certainty, не runtime execution.
Несколько методов дают AMBIGUOUS и все candidates. Неизвестные условия, неполный
Java catalog, context ambiguity и несколько registrations одного метода дают
PARTIAL candidate. Отсутствующая/неподдержанная цель — UNRESOLVED/UNKNOWN.
Schema-to-DTO и parameter links всегда PARTIAL/AMBIGUOUS и INFERRED: serialization,
field compatibility и runtime binding аргументов не доказываются.

## Spring annotations и маршруты

Распознаются imported/qualified `RestController`, `Controller`, `ResponseBody`,
`RequestMapping`, `GetMapping`, `PostMapping`, `PutMapping`, `DeleteMapping`,
`PatchMapping` из стандартных Spring namespaces. Custom composed annotations и
name-only похожие annotations не угадываются. Статические strings/concatenations
и известные final constants берутся из существующего Java constant analysis;
property placeholders, runtime expressions и неизвестные constants остаются
неопределёнными. Java compilation/classpath validation не выполняется.

Class и method prefixes комбинируются; поддержаны массивы paths, `path`/`value`
aliases, RequestMethod enum, consumes/produces и params/headers. Method media
conditions заменяют class conditions, если заданы; HTTP method sets комбинируются.
GET поддерживает implicit HEAD; explicit HEAD имеет приоритет среди совместимых
paths. Ограниченный локальный inheritance/interface lookup использует canonical
concrete methods и исходные annotations, без classpath/reflection. Неоднозначные
базы/mappings не выбираются автоматически. Product paths ограничен 128 на метод;
лимит даёт diagnostic и неполный catalog, а не false unique binding.

Route candidate key заменяет имена целых `{variable}` segments на `{}`. Например,
OpenAPI `/users/{id}` и Java `/users/{userId}` совместимы, но оба оригинальных имени
сохраняются, а parameter alias выводится по позиции. Trailing slash не удаляется;
URI escapes, dot segments, Ant wildcards и composite patterns не нормализуются
догадками. Regex constraints не исполняются; совместимая regex-shaped path остаётся
PARTIAL. GET contract не связывается с POST-only mapping.

Media types сравниваются с учётом case-insensitive type/subtype, wildcard/suffix и
parameters. Charset case-insensitive; другие parameter values сохраняют регистр.
Несовместимые media исключают candidate; неизвестные/отрицательные conditions не
дают RESOLVED. Простые required query/header conditions с literal const/enum могут
быть проверены; остальным нужен runtime request context. Это bounded matcher, не
полная реализация Spring comparator, content negotiation или security rules.

Incoming bindings создаются для прямых `paths` operations, включая известные HTTP
methods в 3.2 additionalOperations. Callbacks/webhooks не приравниваются к incoming
controller routes. QUERY/custom methods сохраняются в D05, но Java handler для них
не угадывается. Path-item operation expansion через `$ref` и functional WebFlux
RouterFunctions не реализуются этим profile; captured body/response/parameter/schema
references используются через существующие D05 edges с cycle bounds.

## Server и application context

Учитываются root/path/operation servers с override, literal HTTP(S)/absolute path
base и известные captured application YAML/YML `server.servlet.context-path` /
`spring.webflux.base-path`. Server prefix не отбрасывается ради совпадения handler.
Различные base paths/profile-specific configuration, malformed/dynamic context и
server variables не превращаются в unique deployment. Никакие URLs не загружаются
и server templates не вычисляются.

Runtime flags, application.properties, environment/config servers, gateway rewrites
и фактический active profile не читаются. Без captured explicit context используется
статический default root; binding всё равно INFERRED/PARTIAL coverage. Known server
URL/service остаётся в Evidence/selector; имя Java package/bean не считается service
identity. Unknown server URI использует deferred symbolic selector.

## DTO и Feign

Request DTO types берутся только из `@RequestBody` parameter signatures. `PathVariable`,
`RequestParam`, `RequestHeader`, `CookieValue` дают explicit parameter bindings.
Response DTO требует RestController/ResponseBody либо HttpEntity/ResponseEntity.
Обычный Controller model object не выдаётся за serialized response body.
Поддержаны declared local classes, arrays и известные single-argument wrappers
Mono/Flux/ResponseEntity/HttpEntity/List/Set/Collection/Optional. Неизвестные generic
wrappers, external DTO classes и arbitrary schema-name matches не разрешаются.
Schema shape/composition/required/nullable/serialization остаются D05 facts,
а не доказанным Java field lineage.

`org.springframework.cloud.openfeign.FeignClient` + Spring mappings или literal
`feign.RequestLine` дают ExternalReference от Java Method с HttpSelector(service,
method, path). Учитываются literal name/value, Feign path и known URL base. Неизвестные
service/method/path/URL дают symbolic selector и diagnostic вместо придуманного GET
или base. Static/private/default implementation methods не объявляются outgoing
Feign requests. Declared client не становится локальным controller target. Ни remote
repository, ни service discovery/runtime bean context не читаются при ingest.

## Lifecycle, diagnostics и проверки

Registry обменивается frozen typed JavaHttpCatalog через D02 catalog phase. Общий
read-only Java declaration/import helper используется BPMN и HTTP profiles; HTTP
catalog не парсит Java повторно. Проекты без supported annotation namespace не
удерживают дополнительный HTTP AST catalog. Java route facts создаются и при
отсутствии OpenAPI. Расширение metadata не меняет семантику Java CALLS/SQL execution;
неопределённые Java calls остаются такими и в составной трассе.

Java HTTP catalog hash учитывает captured sources/types/annotations. При HTTP sources
Java scope инвалидируется консервативно; OpenAPI binding version закрепляет Java
catalog и captured application config hashes, включая malformed config. Stored file
dependencies сохраняют Java/DTO/config/ref provenance. No-change reuse переносит те
же facts/diagnostics; edits, candidate addition/removal и deletion не оставляют stale
handler/DTO references. Publication/read/retention используют общий immutable pipeline.
Preparation failure не создаёт snapshot и не меняет current publication.

Diagnostics: `java.http.PARTIAL_MAPPING`, ROUTE_LIMIT, AMBIGUOUS_BASE;
`openapi.java.UNRESOLVED_HANDLER`, PARTIAL_HANDLER, AMBIGUOUS_HANDLER. Неподдержанная
семантика не скрывается COMPLETE coverage. D05 parser safety/budgets сохраняются.

Интеграционные repeated publications выявили плохой custom plan discovery projector
для свежего snapshot ID, отсутствующего в column statistics. Generic planning
ограничен одним projection statement внутри savepoint с восстановлением caller
plan_cache_mode; scope остальных запросов не меняется. PG15 tests проверяют также
caller `force_custom_plan`, повторные publications и rollback semantics.

Tests: `tests/test_openapi_java_bindings.py`,
`tests/integration/test_openapi_java_storage.py`; D05/D02 regression suites и полный
`pytest --require-postgres`. PG сценарии: default CLI, two-source Evidence,
OpenAPI → handler → service → SQL trace, ambiguity, method/context edits, removal,
immutable historical facts, prepare failure и actual remote-only targets.
