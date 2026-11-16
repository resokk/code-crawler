# code-crawler

MCP-сервер с GraphRAG по коду: обходит кодовую базу, строит граф знаний (файлы, символы, связи) в PostgreSQL и отдаёт его агентам через инструменты MCP.

Две точки входа:

- `code-crawler` — CLI: готовит БД и управляет индексами. Индексы изменяет только он.
- `code-crawler-server` — MCP-сервер: только читает опубликованные индексы.

Подробное описание каждой фичи — в [docs/](docs/).

## Что нужно

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- PostgreSQL 15 с доступными расширениями `pg_trgm` и `btree_gin`
- `git` — для индексации репозиториев по URL

## Подготовка СУБД

1. Создайте базу и роль, под которой будут работать CLI и сервер:

   ```sql
   CREATE ROLE crawler LOGIN PASSWORD '...';
   CREATE DATABASE code_crawler OWNER crawler;
   ```

2. Расширения `pg_trgm` и `btree_gin` ставит миграция (`CREATE EXTENSION IF NOT EXISTS`). Если у роли нет на это прав, установите их заранее от администратора:

   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE EXTENSION IF NOT EXISTS btree_gin;
   ```

3. Выберите схему. Миграции и запросы схему не указывают: объекты создаются и ищутся в текущей схеме подключения. По умолчанию это `public`. Чтобы держать объекты в отдельной схеме, поставьте её первой в `search_path` роли и оставьте в пути схему, где установлены расширения:

   ```sql
   CREATE SCHEMA crawler AUTHORIZATION crawler;
   ALTER ROLE crawler IN DATABASE code_crawler SET search_path = crawler, public;
   ```

   CLI и сервер должны подключаться с одним и тем же `search_path`.

Схему меняют только миграции из репозитория — руками в БД ничего не правится. Подробнее: [docs/db.md](docs/db.md).

## Подготовка окружения

```bash
uv sync
export DATABASE_URL=postgresql://crawler:password@host:5432/code_crawler
uv run code-crawler db init      # создаёт schema_migrations и применяет все миграции
uv run code-crawler db status    # проверяет, что схема соответствует коду
```

После обновления кода недостающие миграции применяет `uv run code-crawler db migrate`.

Переменные окружения:

| Переменная | Кому нужна | Назначение |
| --- | --- | --- |
| `DATABASE_URL` | CLI, сервер | строка подключения к PostgreSQL; обязательна |
| `MCP_ACCESS_POLICY` | сервер | JSON с клиентами, их токенами и правами; обязательна |
| `DISCOVERY_REPOSITORY_KEYS` | сервер | JSON-список репозиториев, доступных глобальному discovery; без неё discovery выключен |
| `FASTMCP_HOST`, `FASTMCP_PORT` | сервер | адрес и порт, по умолчанию `127.0.0.1:8000` |

Секреты задаются только через окружение и в репозиторий не попадают.

## Использование

### Индексация

```bash
uv run code-crawler index ~/work/billing
uv run code-crawler index git@host:group/billing.git --repository-key org/billing
```

Команда разбирает исходники, проверяет результат и атомарно публикует новый снимок индекса. При ошибке прежняя публикация остаётся на месте. Повторный запуск обновляет индекс.

`--repository-key` — имя, под которым репозиторий виден серверу и клиентам. Если его не задать, ключом станет абсолютный путь каталога или URL репозитория, поэтому для общего индекса лучше задавать ключ явно.

Остальные команды и параметры: [docs/cli.md](docs/cli.md), [docs/default-index.md](docs/default-index.md).

### Запуск сервера

Серверу нужна политика доступа: анонимного режима нет. Сгенерируйте токен клиента и его SHA-256:

```bash
python3 -c "import secrets,hashlib; t=secrets.token_urlsafe(32); print(t, hashlib.sha256(t.encode()).hexdigest())"
```

Токен отдайте клиенту, а в политику впишите только хеш:

```bash
export MCP_ACCESS_POLICY='{"principals":[{
  "id":"client-a",
  "token_sha256":"<64 hex-символа>",
  "expires_at":2000000000,
  "repositories":["org/billing"],
  "permissions":["read","evidence","source","discover"]
}]}'
uv run code-crawler-server
```

- `expires_at` — срок действия токена, Unix-время в секундах.
- `repositories` — ключи репозиториев, доступных клиенту; подстановочных знаков нет.
- Политика читается при старте: чтобы изменить права, перезапустите сервер.

Сервер слушает `http://127.0.0.1:8000/mcp`, транспорт — Streamable HTTP без сессий. Вне локальной машины размещайте его за TLS. Подробнее: [docs/server.md](docs/server.md), [docs/mcp-access-control.md](docs/mcp-access-control.md).

### Подключение клиента

Клиент MCP подключается по URL сервера и в каждом запросе передаёт заголовок `Authorization: Bearer <токен>`. Пример конфигурации:

```json
{
  "mcpServers": {
    "code-crawler": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {"Authorization": "Bearer <токен>"}
    }
  }
}
```

Основные инструменты:

| Инструмент | Назначение |
| --- | --- |
| `search_symbols` | символы по точному имени, виду и типам параметров |
| `search_text` | нечёткий поиск по именам |
| `find_callers`, `find_callees` | кто вызывает символ и что вызывает он |
| `find_sql_executions` | места выполнения SQL и тексты запросов |
| `find_table_readers`, `find_table_writers` | запросы, читающие и изменяющие таблицу или колонку |
| `trace_dependency` | обход связей от сущности на глубину 1–6 |
| `get_evidence` | подтверждения и кандидаты одной связи |
| `search_discovery_entries`, `trace_cross_repository` | поиск и обход между репозиториями |

Полный список и контракты результатов: [docs/server.md](docs/server.md), [docs/structural-search.md](docs/structural-search.md).

## Разработка

```bash
uv run pytest           # тесты
uv run ruff check .     # линтер
uv run ruff format .    # форматирование
```

Интеграционные тесты ходят в настоящий PostgreSQL 15 и без `TEST_DATABASE_URL` пропускаются — как их запустить, описано в [docs/db.md](docs/db.md). Правила работы с кодом: [AGENTS.md](AGENTS.md).
