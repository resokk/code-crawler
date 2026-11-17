# Global discovery read API и MCP

Базовый C02 [каталог](discovery-catalog.md) использует существующие
`search_discovery_generations` и `search_discovery_entries` из миграции 0022.
Миграция 0026 добавляет BUILDING→READY sealing, immutable guards и индекс точных
identifier keys. Схема JSON lookup keys и контракт C03 сохранены: единственное
поколение snapshot имеет поле `generation`; read API возвращает его как
`generation_id`. Второго каталога или нового canonical graph нет.

## Lifecycle и versioning

Проектор `discovery/3` строит все entries внутри транзакции canonical publication;
READY выставляется после всех SQL projections. Ошибка откатывает publication и
поколение вместе. Idempotent refresh той же версии ничего не меняет.
`code-crawler discovery refresh REPOSITORY_KEY` обновляет текущий published
snapshot без checkout/повторного анализа. Смена projector version атомарно заменяет
поколение этого snapshot; C03 обнаруживает superseded generation и сохраняет
retention pins исходных snapshots. Прочие репозитории не переиндексируются.

После upgrade уже опубликованные snapshots получают новое поколение при refresh.
Reader явно сообщает PARTIAL availability, если current generation отсутствует
или имеет другую версию. Retired snapshots и их generations не смешиваются с
latest lookup; исторические/pinned/deployment selections предоставляет C03.
GC сохраняет pins C03 и удаляет derivative rows только удаляемых snapshots.
Publication держит repository lock во время repository-local SQL projection;
стоимость проекции линейна по поддержанным facts. Historical migration-prefix
benchmark сохраняет свой прежний baseline.

C01 search documents имеют независимые projection/policy generations. Пересборка
документов не меняет discovery fingerprint. Оба reader сверяют canonical publication;
compound read фиксируется общей read-only REPEATABLE READ транзакцией.

## Точные ключи

Lookup keys case-sensitive: нет lowercase, fuzzy или semantic folding.

- SYMBOL: FQN; qualifier — symbol_kind и parameter_types (ordered array для
  callable, null для остальных). Local variables/parameters исключены. Фильтр
  параметров сравнивает массив целиком, включая порядок и пустую сигнатуру.
- DATABASE: column/table/schema name по object kind; qualifier сохраняет
  database_key, version_key, catalog_name, schema_name, object_kind, table_name,
  column_name и schema_fingerprint. Поиск требует database/version/catalog/schema
  context; регистр identifiers typed schema producer сохраняется.
- HTTP: path и method из typed OPENAPI_OPERATION непосредственно под root paths.
  Namespace — contract_id (OPENAPI_DOCUMENT entity ID); service остаётся null,
  потому что info.title, servers и repository name не являются service binding.
  Фильтр требует method и contract_id либо explicit service. Ключ JSON-key API —
  [null, method, path, contract_id]. Callback/webhook targets не проецируются;
  coverage HTTP всегда PARTIAL, runtime endpoints не доказываются.
- BPMN_PROCESS: XML process id из BPMN_ATTRIBUTE(id); qualifier — XML namespace
  и target_namespace из definitions того же captured файла. Без target_namespace
  поиск может вернуть несколько независимых processes.

- KAFKA_TOPIC: только static topic Symbol с входящим KAFKA_DECLARES_TOPIC от
  KAFKA_DECLARATION с API `org.apache.kafka.clients.admin.NewTopic`. Отправка,
  подписка/listener и client configuration не являются декларациями целей.
  JSON lookup key — `[topic]`, qualifier — optional `cluster`, `environment` из
  D07; `KAFKA` сохранён как совместимый вид с тем же набором деклараций (его
  прежний обязательный cluster filter сохранён). Новый KAFKA_TOPIC допускает
  отсутствие контекста и возвращает все декларации с этим точным именем.
- BPMN_WORKER: только typed `BPMN_WORKER` Symbol с BPMN_WORKER_HANDLER к canonical
  Java Method и literal BPMN_ATTRIBUTE `engine`, `worker_type`. Поддерживаются
  строгие D02 Camunda 7 ExternalTaskSubscription + ExternalTaskHandler и Camunda 8
  JobWorker; ordinary beans, delegates и BPMN tasks не становятся workers.
  JSON lookup key — `[worker_type]`; qualifier содержит `engine`, `handler_id`,
  nullable `namespace`/`service`. Namespace/service не угадываются из package.

Для обоих видов coverage всегда PARTIAL: декларация не доказывает deployment,
activation, broker resource existence или delivery/execution. Точный фильтр по
известному контексту не совпадает с неизвестным. Несколько деклараций сохраняют
AMBIGUOUS. Snapshot/generation и Evidence range остаются частью каждой записи.
Повторяющиеся attribute names исключают декларацию вместо недетерминированного
выбора значения. REFERENCE_DATA/DATASET пока UNSUPPORTED.

Миграция 0032 добавляет BPMN_WORKER и BPMN_WORKER_HANDLER; прошлые миграции не
изменены. Для Kafka достаточно refresh существующего D07 snapshot; для worker
definitions старые Java snapshots надо переиндексировать — refresh не извлекает
новые canonical факты. Java analysis fingerprint включает worker/1 и hash D02
catalog. Старые retained snapshots с уже созданными discovery/3 поколениями
по-прежнему читаются через C03 pinned context; обновление latest их не заменяет.

## API, доступ и неопределённость

`search.search_discovery_entries(conn, kind, lookup_key, *,
allowed_repository_keys, repository_keys=None, qualifier=None, limit=50, offset=0,
expected_fingerprint=None)` читает один SQL/MVCC statement без записи.
Trusted caller обязан передать allowed scope; пустой scope запрещён, requested
repositories должны быть его подмножеством. Не более 32 repository keys,
limit 1–200, offset 0–1000, lookup key до 4096 символов. Вид и qualifier fields
проверяются до SQL. Qualifier filters — nonblank strings или ordered parameter
arrays; null fields следует опускать.

Ответ: items с repository/snapshot/generation/entity identity и source coordinates,
truncated/next_offset, generation_manifest, fingerprint, availability и coverage.
Следующая страница требует expected_fingerprint; при смене поколения чтение
отклоняется вместо смешивания версий. Неизвестные/без публикации/без текущего
поколения repositories дают явную PARTIAL availability.

Каждый item — кандидат с resolution=UNRESOLVED и certainty=UNKNOWN. Несколько
кандидатов дают aggregate AMBIGUOUS; singleton также требует отдельного resolver.
COMPLETE coverage описывает полноту проекции поддержанных сохранённых facts,
а не compiler/runtime полноту исходного анализа. Никаких межрепозиторных рёбер
по совпадению ключа не создаётся. Базовый `discovery.lookup` сохраняет прежний
JSON-key API и candidate-only контракт для C03/других callers.

MCP `search_discovery_entries` использует read-only REPEATABLE READ и trusted
server allowlist `DISCOVERY_REPOSITORY_KEYS` (JSON array repository keys).
Без политики глобальное чтение fail closed; клиент может только сузить scope.
A02 дополнительно проверяет bearer identity, permission discover и пересекает
allowlist с repository membership; см. [mcp-access-control.md](mcp-access-control.md).
Source text, snippets и
Evidence descriptions не копируются. Из BPMN literal facts берутся только
semantic keys id/targetNamespace; универсальный secret detector A06 не заменяется.
