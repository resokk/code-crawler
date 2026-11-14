"""Stateless MCP server: structural queries over published UCM snapshots."""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Literal
from uuid import UUID

import asyncpg
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from fastmcp.server.lifespan import lifespan
from pydantic import Field

from code_crawler import search

EntityId = Annotated[str, Field(pattern=r"^ucm:[0-9a-f]{64}$")]
RepositoryKey = Annotated[str, Field(min_length=1, description="Ключ репозитория")]
Limit = Annotated[int, Field(ge=1, le=search.MAX_LIMIT)]
SymbolKind = Literal[
    "CLASS", "METHOD", "CONSTRUCTOR", "FIELD", "PARAMETER", "LOCAL_VARIABLE"
]


@lifespan
async def _database(server: FastMCP) -> AsyncIterator[dict]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("не задана переменная окружения DATABASE_URL")
    pool = await asyncpg.create_pool(url, min_size=1)
    try:
        yield {"pool": pool}
    finally:
        await pool.close()


mcp = FastMCP("code-crawler", lifespan=_database)


async def _query(
    ctx: Context, run: Callable[[asyncpg.Connection], Awaitable[dict]]
) -> dict:
    async with ctx.lifespan_context["pool"].acquire() as conn:
        try:
            # Сервер индексы только читает: транзакция не даст запросу что-то записать.
            async with conn.transaction(readonly=True):
                return await run(conn)
        except ValueError as error:
            raise ToolError(str(error)) from error


@mcp.tool
async def search_symbols(
    ctx: Context,
    repository_key: RepositoryKey,
    name: Annotated[str, Field(min_length=1)],
    kind: SymbolKind | None = None,
    parameter_types: list[str] | None = None,
    limit: Limit = 50,
) -> dict:
    """Найти символы (классы, методы, поля) по точному простому или полному имени.

    `parameter_types` — имена типов параметров по порядку, чтобы выбрать перегрузку.
    Возвращает id символов для остальных инструментов. `truncated=true` — результатов
    больше, чем `limit`.
    """
    return await _query(
        ctx,
        lambda conn: search.search_symbols(
            conn,
            repository_key,
            name,
            kind=kind,
            parameter_types=parameter_types,
            limit=limit,
        ),
    )


@mcp.tool
async def search_text(
    ctx: Context,
    repository_key: RepositoryKey,
    query: Annotated[str, Field(min_length=1)],
    entity_types: list[
        Literal["SYMBOL", "SOURCE_FILE", "DATABASE_OBJECT", "ORM_MAPPING", "ORM_QUERY"]
    ]
    | None = None,
    snapshot_id: UUID | None = None,
    limit: Limit = 50,
    offset: Annotated[int, Field(ge=0, le=search.MAX_OFFSET)] = 0,
) -> dict:
    """Нечёткий поиск по именам, когда точное имя неизвестно.

    Имена делятся на слова по регистру и знакам: "user id" находит getUserId и
    user_id. Порядок: `match=EXACT`, затем `WORDS` (все слова запроса есть в имени),
    затем `SIMILAR` (похожее написание, опечатки). Следующая страница — тот же
    запрос с `offset=next_offset`. `snapshot_id` выбирает прежнюю опубликованную
    версию вместо текущей.
    """
    return await _query(
        ctx,
        lambda conn: search.search_text(
            conn,
            repository_key,
            query,
            entity_types=entity_types,
            snapshot_id=snapshot_id,
            limit=limit,
            offset=offset,
        ),
    )


@mcp.tool
async def find_callers(
    ctx: Context, repository_key: RepositoryKey, symbol_id: EntityId, limit: Limit = 50
) -> dict:
    """Кто вызывает символ: связи CALLS с Evidence и Coverage.

    Включает неоднозначные вызовы, где символ — один из candidates. Отсутствие
    вызова в ответе не доказывает, что его нет: смотрите `coverage.status`.
    """
    return await _query(
        ctx,
        lambda conn: search.find_callers(conn, repository_key, symbol_id, limit=limit),
    )


@mcp.tool
async def find_callees(
    ctx: Context, repository_key: RepositoryKey, symbol_id: EntityId, limit: Limit = 50
) -> dict:
    """Что вызывает символ: связи CALLS с Evidence и Coverage.

    Вызовы без цели в репозитории (библиотеки, неразрешённые) приходят с
    `resolution=UNRESOLVED`, `reason` и `target=null`; место вызова — в `evidence`.
    """
    return await _query(
        ctx,
        lambda conn: search.find_callees(conn, repository_key, symbol_id, limit=limit),
    )


@mcp.tool
async def find_sql_executions(
    ctx: Context,
    repository_key: RepositoryKey,
    symbol_id: EntityId | None = None,
    limit: Limit = 50,
) -> dict:
    """Места выполнения SQL (всего репозитория или одного метода) и их SQL-тексты.

    Пустой `statements` значит, что текст запроса статически не восстановлен.
    """
    return await _query(
        ctx,
        lambda conn: search.find_sql_executions(
            conn, repository_key, symbol_id=symbol_id, limit=limit
        ),
    )


@mcp.tool
async def find_table_readers(
    ctx: Context,
    repository_key: RepositoryKey,
    table: Annotated[str, Field(min_length=1)],
    column: str | None = None,
    schema: str | None = None,
    limit: Limit = 50,
) -> dict:
    """SQL-запросы, читающие таблицу (или её колонку), и методы, которые их выполняют.

    Пустой `executions` значит, что SQL найден в коде, но его выполнение не доказано.
    """
    return await _query(
        ctx,
        lambda conn: search.find_table_readers(
            conn, repository_key, table, column=column, schema=schema, limit=limit
        ),
    )


@mcp.tool
async def find_table_writers(
    ctx: Context,
    repository_key: RepositoryKey,
    table: Annotated[str, Field(min_length=1)],
    column: str | None = None,
    schema: str | None = None,
    limit: Limit = 50,
) -> dict:
    """SQL-запросы, изменяющие таблицу или колонку (INSERT, UPDATE, DELETE, MERGE, DDL).

    Пустой `executions` значит, что SQL найден в коде, но его выполнение не доказано.
    """
    return await _query(
        ctx,
        lambda conn: search.find_table_writers(
            conn, repository_key, table, column=column, schema=schema, limit=limit
        ),
    )


@mcp.tool
async def trace_dependency(
    ctx: Context,
    repository_key: RepositoryKey,
    entity_id: EntityId,
    direction: Literal["out", "in"] = "out",
    relation_kinds: list[str] | None = None,
    depth: Annotated[int, Field(ge=1, le=search.MAX_DEPTH)] = 2,
    limit: Limit = 100,
) -> dict:
    """Обойти связи от сущности на заданную глубину: `out` — зависимости, `in` — зависящие.

    `relation_kinds` ограничивает виды связей, например ["CALLS", "EXECUTES_SQL",
    "EXECUTES_STATEMENT"]. Обход идёт только по разрешённым связям; неразрешённые
    возвращаются, но не продолжаются.
    """
    return await _query(
        ctx,
        lambda conn: search.trace_dependency(
            conn,
            repository_key,
            entity_id,
            direction=direction,
            relation_kinds=relation_kinds,
            depth=depth,
            limit=limit,
        ),
    )


@mcp.tool
async def get_evidence(
    ctx: Context, repository_key: RepositoryKey, relation_id: EntityId
) -> dict:
    """Полные Evidence, Coverage и candidates одной связи по её `relation_id`."""
    return await _query(
        ctx, lambda conn: search.get_evidence(conn, repository_key, relation_id)
    )


def main() -> None:
    mcp.run(transport="http", stateless_http=True)
