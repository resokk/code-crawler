# MCP-сервер

Сервер `code-crawler` на `fastmcp`. Транспорт — Streamable HTTP в режиме stateless: каждый запрос самодостаточен, сессий нет.

Сейчас это каркас: инструментов, ресурсов и промптов нет.

## Запуск

```bash
uv run code-crawler-server
```

Слушает `http://127.0.0.1:8000/mcp` (значения `fastmcp` по умолчанию). Хост и порт меняются переменными окружения `FASTMCP_HOST` и `FASTMCP_PORT`.

Переходный stateless reader `code_crawler.legacy.read_graph` поддерживает
выбранный в БД legacy/UCM backend. Он пока доступен через CLI `show-index` и
библиотечный API; новых MCP tools этот change не добавляет. Нормативный UCM query
engine и MCP-инструменты будут отдельными changes.
