# BPMN 2.0 → UCM

`BpmnSourceAdapter` включён в `adapters list`, `index` и `index-sources`.
Маршруты: `.bpmn`, `.bpmn20.xml`, `.xml` (case-sensitive). XML распознаётся
по expanded QName корня `{http://www.omg.org/spec/BPMN/20100524/MODEL}definitions`,
независимо от namespace prefix. Другой корректный XML получает metadata и
SourceAnalysis с UNSUPPORTED, без semantic facts. Version: `bpmn/1`.

## Факты и Evidence

Используется существующий UCM, без отдельного графа и прямых записей из адаптера.
Каждый XML element становится `Symbol(symbol_kind=BPMN_ELEMENT)`; `qualified_name`
и `type_ref.name` содержат expanded QName. Это сохраняет процессы, start/end и
intermediate events, service/user tasks, subprocesses, gateways, sequence flows,
conditions, variables, input/output mappings и неизвестные extension elements.
Иерархия задаётся `CONTAINS`. Каждый атрибут — `Value(LITERAL)` со своим expanded
QName в name, связанный через `BPMN_ATTRIBUTE`; непосредственный текст элемента
(включая CDATA, без форматирующего whitespace-only текста) — `BPMN_TEXT`.
Значения атрибутов могут быть пустыми. XML namespace declarations не являются
атрибутами; их влияние отражено в expanded QName. Prefix внутри значений QName
сохраняется как текст и не разрешается автоматически.

Sequence flow — отдельный addressable symbol. `BPMN_FLOW_SOURCE` и
`BPMN_FLOW_TARGET` ведут от него к flow nodes в одном process/subProcess/transaction.
Condition expression остаётся дочерним symbol и literal text; два перехода с
одинаковыми endpoints не сливаются. Missing, неподходящий или вышедший за границы
контейнера endpoint даёт `bpmn.INVALID_FLOW`; для такого flow не создаётся ни одна
endpoint relation. Синтаксические facts этого XML сохраняются.

Все facts имеют SourceRange по исходным UTF-8 byte coordinates; relations и
ExternalReferences содержат Evidence, Coverage и Resolution. Range XML element
охватывает полный элемент; attributes/text используют range владельца, без ложной
точности. ID-bearing symbols стабильны по repository/path/XML ID; anonymous nodes
имеют структурный путь от ближайшего ID-bearing предка. Неизменные документы дают
те же IDs, изменение порядка anonymous siblings может изменить их IDs.

## Отложенные ссылки

`callActivity@calledElement` разрешается в локальный process по точному XML ID:
`BPMN_CALLS_PROCESS`. Иначе создаётся unresolved `ExternalReference` с существующим
`SymbolSelector(qualified_name="bpmn.process::<value>")`.
Camunda 7 `serviceTask@camunda:topic`, Camunda 8/Zeebe `taskDefinition@type`
создают `bpmn.worker::<value>`. Camunda `class`, `delegateExpression`, `expression`
получают соответствующий префикс `bpmn.<attribute>::<value>`.
Engine namespaces: `http://camunda.org/schema/1.0/bpmn` и
`http://camunda.org/schema/zeebe/1.0`. Другие engine hints остаются XML facts.
Динамические selectors сохраняются с UNKNOWN certainty. Статический literal
selector — STATIC_PROVEN факт наличия ссылки, а не доказательство существования
worker или Java binding. Репозитории извне не читаются; cross-snapshot relations
не создаются. Java binding относится к отдельному change d02.

## Безопасность, Coverage и lifecycle

Парсер стандартной библиотеки Expat работает только с captured bytes в worker
thread. Только UTF-8; максимум 8 MiB, 128 уровней и 20 000 элементов. DTD,
internal/external entity declarations запрещены до expansion; внешние ресурсы,
XInclude, schemaLocation, scripts и expressions не загружаются и не исполняются.
Predefined XML entities и numeric character references разрешены.

Malformed XML, DTD, превышение лимита, неподдержанная encoding дают ERROR
`bpmn.INVALID_XML`; duplicate XML IDs — `bpmn.DUPLICATE_ID`. В этих случаях
документ не отдаёт semantic facts, но SourceAnalysis с diagnostics сохраняется
и может публиковаться. Весь формат имеет явное `bpmn.schema/PARTIAL`: expressions
и extensions сохраняются без исполнения, XSD и engine semantics не валидируются.
Это не runtime control-flow или доказанное выполнение task.

Миграция `0020_bpmn_schema_adapter.sql` расширяет typed symbol/relation registry;
существующие tables, ingestion, source ownership и atomic publication переиспользуются.
Analysis version не зависит от содержимого других файлов: изменение BPMN
переанализирует этот файл, no-change reuse сохраняет facts/diagnostics, удаление
убирает facts только из нового snapshot. Repository/path входят в identities.

Проверки: `tests/test_bpmn_adapter.py`,
`tests/integration/test_bpmn_storage.py` (PG15: publish/read/reuse/edit/delete,
repository isolation, producer failure и неизменность published facts).
