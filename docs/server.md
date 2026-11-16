# MCP-сервер

Сервер `code-crawler` на `fastmcp`. Транспорт — Streamable HTTP в режиме stateless: каждый запрос самодостаточен, сессий нет.

## Запуск

```bash
DATABASE_URL=postgresql://... uv run code-crawler-server
```

Слушает `http://127.0.0.1:8000/mcp` (значения `fastmcp` по умолчанию). Хост и порт меняются переменными окружения `FASTMCP_HOST` и `FASTMCP_PORT`.

Пул соединений PostgreSQL создаётся один раз при старте процесса из `DATABASE_URL`;
без переменной сервер не запускается. Пул и deployment policy общие; identity
и права пользователя из запросов не сохраняются в сессиях.

## Инструменты

Change `mcp-structural-tools` плана [2.0](development-plan-v2.md). Инструменты —
тонкая обёртка над `code_crawler.search`; контракт результатов описан в
[structural-search.md](structural-search.md).

| Инструмент | Назначение |
| --- | --- |
| `search_discovery_entries` | глобальные кандидаты по точным ключам в разрешённых published generations; [контракт](global-discovery-catalog.md) |
| `search_symbols` | символы по точному простому или полному имени, виду и типам параметров |
| `search_text` | нечёткий поиск по именам с ранжированием и страницами, см. [lexical-search.md](lexical-search.md) |
| `find_callers` | кто вызывает символ |
| `find_callees` | что вызывает символ |
| `find_sql_executions` | места выполнения SQL и их тексты |
| `find_table_readers` | запросы, читающие таблицу или колонку, и их исполнители |
| `find_table_writers` | запросы, изменяющие таблицу или колонку, и их исполнители |
| `trace_cross_repository` | ограниченный обход в явном контексте версий; [контракт C06](cross-repository-graph.md) |
| `trace_dependency` | обход связей от сущности на глубину 1–6, наружу или внутрь |
| `get_evidence` | Evidence, Coverage и candidates одной связи |

Правила:

- Repository-scoped инструменты принимают `repository_key` и читает только опубликованный
  snapshot этого репозитория. Сервер ничего не пишет: запрос идёт в read-only
  REPEATABLE READ транзакции.
- Аргументы проверяются до запроса: ID сущностей — `ucm:` и 64 hex-символа,
  `limit` — 1–200, `depth` — 1–6, `offset` — 0–1000. Путей к файлам инструменты не принимают.
- Неполнота явная: `truncated`, `resolution`/`reason`/`candidates` у связей,
  `coverage.status` с причинами, пустые `statements` и `executions`.
- Неизвестный репозиторий, репозиторий без публикации и неизвестная связь
  возвращаются как ошибка инструмента, а не как пустой результат.

Аутентификация обязательна: bearer token и серверная repository policy.
Отсутствующая identity или право отклоняются до получения соединения с БД.
См. [mcp-access-control.md](mcp-access-control.md).

Переходный stateless reader `code_crawler.legacy.read_graph` поддерживает
выбранный в БД legacy/UCM backend и доступен через CLI `show-index`.

Один tool call читает согласованную MVCC версию, включая concurrent publication/GC.
Полный типизированный библиотечный reader и source proof retrieval описаны в
[canonical-read.md](canonical-read.md); формат существующих MCP tools не меняется.

Глобальный discovery выключен по умолчанию. `DISCOVERY_REPOSITORY_KEYS='["org/a","org/b"]'`
задаёт явный trusted scope сервера, пересекаемый с правами principal.
Отсутствующая политика запрещает discovery,
клиентский `repository_keys` может только сузить scope. Discovery выдаёт кандидатов
с UNKNOWN certainty, включая единственный match; snapshot/generation manifest,
PARTIAL availability и pagination fingerprint возвращаются явно.

Поиск внутри MCP-транзакции держит shared snapshot lease до завершения tool call.
GC пропускает используемую версию; следующий вызов GC может удалить её после
освобождения lease. Прямым SQL-читателям доступен `snapshots.pin_snapshot` внутри
транзакции. Подробности и отчёт очистки: [ingest-jobs.md](ingest-jobs.md).

SQL-инструменты возвращают отдельные `discovery_status`, `execution_link_status`
и `target_resolution`; Evidence/certainty сохранённых связей доступны в relation.
См. [контракт уверенности SQL](structural-search.md#контракт-уверенности-sql-a04)
с примерами формулировок: обнаруженный SQL и статический sink не доказывают runtime execution.

A03 extends `find_table_readers`/`find_table_writers` with explicit `mode` and
`database_key`, `schema_version_key`, `database_object_id`. Default name search
remains compatible; exact mode uses authorized published snapshot bindings only.
[Selector, uncertainty and response contract](structural-search.md#database-qualified-sql-access-search-a03).

A06 applies mandatory masking to all tool result payloads after authorized SQL,
including SQL, Evidence descriptions and cross-repository traversal. Affected
responses add data_security with PARTIAL derivative status and safe coordinates;
original canonical Coverage/Certainty is retained. No RPC argument disables this
policy. Source permission is used only by the explicit authorized source reader.
See [source-data-security.md](source-data-security.md).
