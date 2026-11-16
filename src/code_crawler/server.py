"""Stateless MCP server: structural queries over published UCM snapshots."""

import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Literal
from uuid import UUID

import asyncpg
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.lifespan import lifespan
from pydantic import BeforeValidator, Field

from code_crawler import search
from code_crawler.access import (
    Permission,
    PolicyVerifier,
    configure_audit,
    load_policy,
)
from code_crawler.resolver_context import ResolverContext
from code_crawler.ucm import RelationKind


def _resolver_context(value: ResolverContext | dict) -> ResolverContext:
    # MCP validates Python JSON values; canonical strict models require JSON mode.
    if isinstance(value, dict):
        return ResolverContext.model_validate_json(json.dumps(value))
    return value


McpResolverContext = Annotated[ResolverContext, BeforeValidator(_resolver_context)]

EntityId = Annotated[str, Field(pattern=r"^ucm:[0-9a-f]{64}$")]
RepositoryKey = Annotated[str, Field(min_length=1, description="Ключ репозитория")]
Limit = Annotated[int, Field(ge=1, le=search.MAX_LIMIT)]
SymbolKind = Literal[
    "CLASS", "METHOD", "CONSTRUCTOR", "FIELD", "PARAMETER", "LOCAL_VARIABLE"
]


@lifespan
async def _database(server: FastMCP) -> AsyncIterator[dict]:
    policy = load_policy()
    configure_audit()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("не задана переменная окружения DATABASE_URL")
    configured = os.environ.get("DISCOVERY_REPOSITORY_KEYS")
    discovery_keys = (
        search._discovery_scope(json.loads(configured))
        if configured is not None
        else ()
    )
    pool = await asyncpg.create_pool(url, min_size=1)
    try:
        yield {
            "pool": pool,
            "discovery_repository_keys": discovery_keys,
            "access_policy": policy,
        }
    finally:
        await pool.close()


mcp = FastMCP(
    "code-crawler", lifespan=_database, auth=PolicyVerifier(), mask_error_details=True
)


async def _query(
    ctx: Context,
    run: Callable[[asyncpg.Connection], Awaitable[dict]],
    repository_key: str | None = None,
    *,
    permission: Permission = "read",
    discovery_keys: tuple[str, ...] | None = None,
) -> dict:
    policy = ctx.lifespan_context["access_policy"]
    token = get_access_token()
    try:
        principal = policy.authenticate(token.token if token else None)
        if repository_key is None and discovery_keys is None:
            raise PermissionError("access denied")
        targets = discovery_keys if discovery_keys is not None else (repository_key,)
        policy.authorize(principal, permission, targets)
    except PermissionError:
        raise ToolError("access denied") from None
    async with ctx.lifespan_context["pool"].acquire() as conn:
        try:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                return await run(conn)
        except (
            ValueError,
            PermissionError,
            RuntimeError,
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
        ):
            raise ToolError("query failed") from None


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
        repository_key=repository_key,
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
        repository_key=repository_key,
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
        repository_key=repository_key,
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
        repository_key=repository_key,
    )


@mcp.tool
async def find_sql_executions(
    ctx: Context,
    repository_key: RepositoryKey,
    symbol_id: EntityId | None = None,
    limit: Limit = 50,
) -> dict:
    """Места выполнения SQL (всего репозитория или одного метода) и их SQL-тексты.

    Пустой `statements` и coverage SQL_TEXT_NOT_RECOVERED означают неизвестный SQL.
    sink_relations сохраняет Evidence/certainty. Статическая связь не доказывает
    выполнение во время работы приложения.
    """
    return await _query(
        ctx,
        lambda conn: search.find_sql_executions(
            conn, repository_key, symbol_id=symbol_id, limit=limit
        ),
        repository_key=repository_key,
    )


@mcp.tool
async def find_table_readers(
    ctx: Context,
    repository_key: RepositoryKey,
    table: Annotated[str, Field(min_length=1)] | None = None,
    column: str | None = None,
    schema: str | None = None,
    limit: Limit = 50,
    mode: search.AccessMode = "SYNTACTIC_NAME",
    database_key: str | None = None,
    schema_version_key: str | None = None,
    database_object_id: EntityId | None = None,
) -> dict:
    """SQL-запросы, читающие таблицу (или её колонку), и методы, которые их выполняют.

    discovery_status=FOUND означает обнаружение SQL. execution_link_status отдельно
    показывает статическую связь с sink; NOT_ESTABLISHED — связь не доказана.
    target_resolution относится только к DB-цели. Evidence/certainty — в relation.
    SYNTACTIC_NAME сопоставляет SQL-имена. RESOLVED_DATABASE_OBJECT требует
    database_key/schema_version_key и table либо snapshot-local database_object_id.
    Пустой `executions` значит, что SQL найден в коде, но его выполнение не доказано.
    """
    return await _query(
        ctx,
        lambda conn: search.find_table_readers(
            conn,
            repository_key,
            table,
            column=column,
            schema=schema,
            limit=limit,
            mode=mode,
            database_key=database_key,
            schema_version_key=schema_version_key,
            database_object_id=database_object_id,
        ),
        repository_key=repository_key,
    )


@mcp.tool
async def find_table_writers(
    ctx: Context,
    repository_key: RepositoryKey,
    table: Annotated[str, Field(min_length=1)] | None = None,
    column: str | None = None,
    schema: str | None = None,
    limit: Limit = 50,
    mode: search.AccessMode = "SYNTACTIC_NAME",
    database_key: str | None = None,
    schema_version_key: str | None = None,
    database_object_id: EntityId | None = None,
) -> dict:
    """SQL-запросы, изменяющие таблицу или колонку (INSERT, UPDATE, DELETE, MERGE, DDL).

    discovery_status=FOUND означает обнаружение SQL. execution_link_status отдельно
    показывает статическую связь с sink; NOT_ESTABLISHED — связь не доказана.
    target_resolution относится только к DB-цели. Evidence/certainty — в relation.
    SYNTACTIC_NAME сопоставляет SQL-имена. RESOLVED_DATABASE_OBJECT требует
    database_key/schema_version_key и table либо snapshot-local database_object_id.
    Пустой `executions` значит, что SQL найден в коде, но его выполнение не доказано.
    """
    return await _query(
        ctx,
        lambda conn: search.find_table_writers(
            conn,
            repository_key,
            table,
            column=column,
            schema=schema,
            limit=limit,
            mode=mode,
            database_key=database_key,
            schema_version_key=schema_version_key,
            database_object_id=database_object_id,
        ),
        repository_key=repository_key,
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
        repository_key=repository_key,
    )


@mcp.tool
async def get_evidence(
    ctx: Context, repository_key: RepositoryKey, relation_id: EntityId
) -> dict:
    """Полные Evidence, Coverage и candidates одной связи по её `relation_id`."""
    return await _query(
        ctx,
        lambda conn: search.get_evidence(conn, repository_key, relation_id),
        repository_key,
        permission="evidence",
    )


@mcp.tool
async def search_discovery_entries(
    ctx: Context,
    kind: Literal[
        "SYMBOL",
        "DATABASE",
        "BPMN_PROCESS",
        "HTTP",
        "BPMN_WORKER",
        "REFERENCE_DATA",
        "KAFKA",
    ],
    lookup_key: Annotated[str, Field(min_length=1, max_length=4096)],
    repository_keys: list[str] | None = None,
    qualifier: dict | None = None,
    limit: Limit = 50,
    offset: Annotated[int, Field(ge=0, le=search.MAX_OFFSET)] = 0,
    expected_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    | None = None,
) -> dict:
    """Найти потенциальные цели в разрешённых published репозиториях.

    Точный lookup_key — FQN, DB identifier, HTTP path или BPMN process id. qualifier уточняет
    signature/namespace/context. Совпадение не доказывает dependency. Доступ задаёт
    server DISCOVERY_REPOSITORY_KEYS; клиент может только сузить scope. Следующая
    страница требует fingerprint предыдущей, чтобы не смешать поколения.
    """
    policy = ctx.lifespan_context["access_policy"]
    token = get_access_token()
    try:
        principal = policy.authenticate(token.token if token else None)
    except PermissionError:
        raise ToolError("access denied") from None
    allowed = tuple(
        sorted(
            set(principal.repositories)
            & set(ctx.lifespan_context.get("discovery_repository_keys", ()))
        )
    )
    requested = tuple(repository_keys) if repository_keys is not None else allowed
    if not requested or not set(requested) <= set(allowed):
        from code_crawler.access import audit

        audit(principal.id, "discover", False, requested)
        raise ToolError("access denied")
    return await _query(
        ctx,
        lambda conn: search.search_discovery_entries(
            conn,
            kind,
            lookup_key,
            allowed_repository_keys=list(allowed),
            repository_keys=repository_keys,
            qualifier=qualifier,
            limit=limit,
            offset=offset,
            expected_fingerprint=expected_fingerprint,
        ),
        permission="discover",
        discovery_keys=requested,
    )


@mcp.tool
async def trace_cross_repository(
    ctx: Context,
    repository_key: RepositoryKey,
    entity_id: EntityId,
    context: McpResolverContext,
    depth: Annotated[int, Field(ge=1, le=12)] = 4,
    fanout: Annotated[int, Field(ge=1, le=50)] = 20,
    max_nodes: Annotated[int, Field(ge=1, le=500)] = 100,
    max_repository_hops: Annotated[int, Field(ge=0, le=8)] = 2,
    max_results: Annotated[int, Field(ge=1, le=500)] = 100,
    timeout_ms: Annotated[int, Field(ge=1, le=30000)] = 5000,
    relation_kinds: list[RelationKind] | None = None,
) -> dict:
    """Обойти зависимости в явных версиях разрешённых репозиториев.

    Неоднозначные кандидаты возвращаются без продолжения пути. Каждый переход
    сохраняет Evidence и snapshots; лимиты возвращают частичный результат.
    Требуются read/discover, membership всех версий контекста и server scope.
    """

    policy = ctx.lifespan_context["access_policy"]
    token = get_access_token()
    targets = tuple(
        sorted({repository_key, *(s.repository_key for s in context.selections)})
    )
    try:
        principal = policy.authenticate(token.token if token else None)
        policy.authorize(principal, "discover", targets)
        allowed = frozenset(principal.repositories) & frozenset(
            ctx.lifespan_context.get("discovery_repository_keys", ())
        )
        if not set(targets) <= allowed:
            from code_crawler.access import audit

            audit(principal.id, "discover", False, targets)
            raise PermissionError("access denied")
    except PermissionError:
        raise ToolError("access denied") from None

    async def run(conn):
        result = await search.trace_cross_repository(
            conn,
            repository_key,
            entity_id,
            context,
            allowed_repositories=allowed,
            depth=depth,
            fanout=fanout,
            max_nodes=max_nodes,
            max_repository_hops=max_repository_hops,
            max_results=max_results,
            timeout_ms=timeout_ms,
            relation_kinds=tuple(relation_kinds or ()),
        )
        return result.model_dump(mode="json")

    return await _query(ctx, run, discovery_keys=targets)


def main() -> None:
    mcp.run(transport="http", stateless_http=True)
