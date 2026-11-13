# MCP-сервер

Сервер `code-crawler` на `fastmcp`. Транспорт — Streamable HTTP в режиме stateless: каждый запрос самодостаточен, сессий нет.

Сейчас это каркас: инструментов, ресурсов и промптов нет.

## Запуск

```bash
uv run code-crawler-server
```

Слушает `http://127.0.0.1:8000/mcp` (значения `fastmcp` по умолчанию). Хост и порт меняются переменными окружения `FASTMCP_HOST` и `FASTMCP_PORT`.
