# BPMN → Java bindings

`BpmnSourceAdapter` дополняет XML facts из [bpmn-schema.md](bpmn-schema.md)
локальными привязками к существующим canonical Java Symbols. В CLI включён по
умолчанию вместе с Java adapter. Парсер Java, SQL analysis, storage и publication
не дублируются. Связь с handler — объявленная конфигурация, не доказанное выполнение.

```bash
uv run code-crawler index-sources /repo --repository-key org/repo \
  --java-profile execution --bpmn-profile camunda7 --publish
```

`index` принимает тот же `--bpmn-profile`; его значение сохраняется в ingest job
и восстанавливается при retry. Старые задания без этого поля используют `auto`.
Programmatic API: `AdapterRegistry((JavaSourceAdapter(profile="execution"),
BpmnSourceAdapter(profile="camunda7")))`. Отдельный BPMN adapter сохраняет deferred
selectors, если Java adapter или совместимая локальная цель отсутствуют.

## Профили и версии

| Profile | Поддержанные декларации |
| --- | --- |
| `auto` | перечисленные namespaces/API; версия runtime не угадывается |
| `camunda7` | `camunda:class`, простой `delegateExpression`, literal topic; JavaDelegate и ExternalTaskHandler |
| `camunda8` | Zeebe taskDefinition type; Java JobWorker/Variable annotations |
| `flowable6`, `flowable7` | Flowable class/delegateExpression, общий JavaDelegate API; external-worker topic остаётся deferred |

Namespaces: Camunda `http://camunda.org/schema/1.0/bpmn`,
Zeebe `http://camunda.org/schema/zeebe/1.0`, Flowable `http://flowable.org/bpmn`.
Flowable 6/7 используют один поддержанный статический Java API, но явный profile
отдельно входит в fingerprint. Namespace вне выбранного profile даёт
`bpmn.java.UNSUPPORTED_PROFILE`, unresolved relation и deferred selector.
Classpath, installed engine version, deployment и Spring context не загружаются.

Версии: adapter `bpmn/2`, schema analyzer `bpmn/1`, binding capability
`bpmn.java/1`, Java catalog `java.bpmn.handlers/1:<sha256>`.
`SourceAnalysis.analysis_version` закрепляет profile и Java catalog hash.
Coverage `bpmn.java.bindings` всегда PARTIAL; для не-BPMN XML — UNSUPPORTED.

## Java handlers и beans

BPMN `serviceTask` получает `BPMN_HANDLER` к canonical Method Symbol:

- Camunda 7: реализация `org.camunda.bpm.engine.delegate.JavaDelegate` с public
  instance `void execute(org.camunda.bpm.engine.delegate.DelegateExecution)`.
- Flowable: соответствующие `org.flowable.engine.delegate.JavaDelegate` и
  `DelegateExecution`, с такой же сигнатурой.
- Camunda 7 external worker: imported/qualified
  `org.camunda.bpm.client.spring.annotation.ExternalTaskSubscription` с literal
  `value`/`topicName`, реализация ExternalTaskHandler и совместимый execute с
  ExternalTask/ExternalTaskService из `org.camunda.bpm.client.task`.
- Camunda 8: nonstatic method с `@JobWorker(type="literal")` из
  `io.camunda.zeebe.spring.client.annotation` или `io.camunda.spring.client.annotation`.
  Literal `enabled=false` и abstract owners не становятся локальными workers.

Spring beans распознаются по imported/qualified `Component`, `Service`,
`javax.inject.Named`, `jakarta.inject.Named`, а также `@Bean` factory return type.
Поддержаны literal names/aliases, массив aliases, стандартное default bean name с
сохранением двух начальных uppercase букв. Неизвестные meta-annotations, dynamic
constants, XML bean configuration, component scan и conditional registration не
разрешаются. Single imports/current package/local nested types и единственный
wildcard import поддержаны консервативно; неизвестные/conflicting imports не
превращаются в name-only match.

`delegateExpression` поддерживает только целиком `${bean}`/`#{bean}`. Property,
method invocation, indexing и прочие выражения не вычисляются и не угадываются.
`expression` не приравнивается к вызову JavaDelegate.execute. Class binding требует
совместимого interface и сигнатуры; одно совпадение имени execute недостаточно.
Локальная inheritance chain поддержана до 64 типов, с Evidence её деклараций;
неизвестная/неоднозначная база не выбирается автоматически.

Единственный совместимый target: RESOLVED с INFERRED certainty. Два разных
совместимых target: AMBIGUOUS с обоими candidates. Несколько регистраций одного
canonical метода, неполный Java catalog или конфликтующие selectors: PARTIAL с
candidate вместо ложного unique target. Java parser errors исключают файл из
symbols-profile catalog; более строгие Java profiles сохраняют прежний fail-fast.

Каждая handler relation содержит Evidence из BPMN и Java (contract/method,
bean/worker annotation и, при необходимости, factory/inheritance). Java Symbols
берутся из результата текущего Java profile, с его canonical IDs. Runtime
registration, dynamic dispatch и выполнение не становятся STATIC_PROVEN.

## Переменные и data lineage

Typed facts расширяют существующие Symbol/Value, без opaque JSON:

| Relation | Смысл |
| --- | --- |
| `BPMN_INPUT_MAPPING`, `BPMN_OUTPUT_MAPPING` | activity → XML mapping Symbol |
| `BPMN_READS_VARIABLE`, `BPMN_WRITES_VARIABLE` | handler Method → contextual variable Value |
| `BPMN_VARIABLE_BINDING` | XML mapping → candidate variable Values |

Поддержаны Camunda inputOutput/inputParameter/outputParameter, Zeebe
ioMapping/input/output и Camunda/Flowable in/out. Исходные names, sources, targets
и expressions остаются адресуемыми XML facts из D01.

Java access извлекается только из getVariable/getVariableLocal/setVariable/
setVariableLocal на прямо указанном параметре известного DelegateExecution,
из чтения ExternalTask и из Camunda 8 `@Variable(name/value)` на worker parameter.
Name-only методы другого receiver не считаются process-variable access. Лямбды,
вложенные классы, aliases, helper-method propagation и return-object mapping не
выводятся автоматически. Dynamic variable name становится UNKNOWN Value с
PARTIAL coverage и `bpmn.java.DYNAMIC_VARIABLE`.

Input target name либо простой output source `${name}`/`#{name}`/`=name`
сопоставляется с Java access соответствующего направления. Это только candidate
name match: `BPMN_VARIABLE_BINDING` имеет PARTIAL/AMBIGUOUS и INFERRED, с Evidence
из обоих файлов. Сложный output expression не выдаётся за конкретный variable.
STATIC_PROVEN у input/output mapping означает наличие XML configuration, а не
доказанную передачу данных. Variable facts принадлежат BPMN file/task; Java access
locations сохраняются в Evidence, чтобы incremental ownership не смешивался.

## Registry, incremental и publication

После независимого prepare registry вызывает optional `CatalogProvider.export_catalogs`
и `CatalogConsumer.with_catalogs` для непустого `catalog_keys`. Передаются frozen typed AdapterCatalog objects,
только tuples/frozen values, через read-only mapping. Проверяются uniqueness,
captured SourceFile identity/hash, adapter ownership, SourceRange bounds и version
stability. CPU validation и analysis работают в worker threads; ни DB connection,
ни root, ни mutable Java AST не передаются потребителю.

Без BPMN XML root binding catalog не строится: тот же безопасный XML parser
проверяет только корневой element, сохраняя namespace/DTD/encoding rules. Это
не заставляет symbols-only Java projects удерживать полный AST catalog из-за
одного pom.xml. Полный XML parsing и diagnostics выполняются обычным analyze.

Java provider использует AST уже выполненного canonical extraction; symbols profile
переиспользует этот extraction и для своих facts. Java catalog фиксирует captured
files, compatible handlers, annotations, variables и исключённые malformed files.
BPMN fingerprint включает его hash. Добавление, удаление, изменение Java annotation
или body консервативно переанализирует routed BPMN files; локальные file dependencies
также сохраняются. Изменение только BPMN/profile не требует переиндексации Java facts
в incremental storage. No-change reuse переносит facts и diagnostics.
Подготовка Java catalog всё ещё выполняется при каждом index, как у существующих
canonical Java profiles; bounded streaming catalog не заявляется.

Индексация не читает другие repositories/snapshots. Отсутствующие workers, beans,
classes/processes сохраняются как unresolved ExternalReference с role-prefixed
SymbolSelector. После локального разрешения соответствующий schema selector
заменяется contextual binding; process selectors D01 сохраняются. Динамические и
неподдержанные bindings имеют `bpmn.java.DYNAMIC_SELECTOR`/UNSUPPORTED_PROFILE;
conflicts — CONFLICTING_BINDINGS; исключённые Java files — PARTIAL_JAVA_CATALOG.
Неизвестные XML engine extensions остаются schema facts. Безопасный XML contract
D01 (DTD/XXE rejection, UTF-8, size/depth/element bounds) сохраняется.

Миграция `0024_bpmn_java_bindings.sql` расширяет только normative relation registry.
Существующие UCM tables, immutable snapshots, validation и atomic publication
переиспользуются. Ошибка catalog preparation/binding не создаёт новый snapshot и
не двигает опубликованный pointer. Published relations читаются существующими
reader/search/MCP APIs; trace_dependency проходит BPMN_HANDLER → Java EXECUTES_SQL,
сохраняя Certainty/Coverage. AMBIGUOUS/UNRESOLVED target не обходится как resolved.
BPMN adapter сам не создаёт SQL execution, SQL parsing или Java CALLS.

Проверки: `tests/test_bpmn_java_bindings.py`, `tests/test_adapter_catalogs.py`,
`tests/integration/test_bpmn_java_storage.py` (PG15: CLI, publish/read/trace,
reuse, ambiguity, annotation rename, profile change, deletion, parser/binding
failure, immutable old snapshots и remote-only targets).

## Worker discovery (C11)

Java profiles сохраняют поддержанные `WORKER` registrations из того же D02 catalog
как отдельные BPMN_WORKER Symbols, даже без BPMN XML в repository. Связь
BPMN_WORKER_HANDLER ведёт к прежнему canonical Method и сохраняет Evidence
annotation + method/interface. Literal engine и worker_type — BPMN_ATTRIBUTE
Values. Dynamic placeholders, enabled=false, abstract/static workers, неверные
imports и обычные beans не создают discovery definitions.

Capability `bpmn.worker.declarations`, версия `bpmn.worker/1`, всегда PARTIAL.
Правила локального BPMN_HANDLER и его Resolution/Certainty не изменены.
Worker catalog hash входит в Java analysis fingerprint; изменение registration
инвалидирует reuse. Проекты без признаков worker annotations не строят этот
catalog дополнительно. C02 discovery/3 и C04 resolver/3 ищут declarations
в выбранных C03 snapshots, без cross-repository canonical relations.
