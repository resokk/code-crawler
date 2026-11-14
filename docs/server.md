# MCP-сервер

Сервер `code-crawler` на `fastmcp`. Транспорт — Streamable HTTP в режиме stateless: каждый запрос самодостаточен, сессий нет.

## Запуск

```bash
DATABASE_URL=postgresql://... uv run code-crawler-server
```

Слушает `http://127.0.0.1:8000/mcp` (значения `fastmcp` по умолчанию). Хост и порт меняются переменными окружения `FASTMCP_HOST` и `FASTMCP_PORT`.

Пул соединений PostgreSQL создаётся один раз при старте процесса из `DATABASE_URL`;
без переменной сервер не запускается. Между запросами в памяти ничего не хранится.

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

Аутентификации и разграничения доступа к репозиториям нет: любой клиент сервера
читает любой опубликованный репозиторий (change `repository-access-control`, R6).

Переходный stateless reader `code_crawler.legacy.read_graph` поддерживает
выбранный в БД legacy/UCM backend и доступен через CLI `show-index`.

Один tool call читает согласованную MVCC версию, включая concurrent publication/GC.
Полный типизированный библиотечный reader и source proof retrieval описаны в
[canonical-read.md](canonical-read.md); формат существующих MCP tools не меняется.

Глобальный discovery выключен по умолчанию. `DISCOVERY_REPOSITORY_KEYS='["org/a","org/b"]'`
задаёт явный trusted scope сервера. Отсутствующая политика запрещает discovery,
клиентский `repository_keys` может только сузить scope. Discovery выдаёт кандидатов
с UNKNOWN certainty, включая единственный match; snapshot/generation manifest,
PARTIAL availability и pagination fingerprint возвращаются явно.
