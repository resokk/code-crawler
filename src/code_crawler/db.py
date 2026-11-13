import os
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Произвольный ключ advisory-блокировки.
_MIGRATION_LOCK = 4_217_001


async def connect(variable: str = "DATABASE_URL") -> asyncpg.Connection:
    url = os.environ.get(variable)
    if not url:
        raise RuntimeError(f"не задана переменная окружения {variable}")
    return await asyncpg.connect(url)


def migration_names() -> list[str]:
    return sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))


def diff_migrations(known: list[str], applied: set[str]) -> tuple[list[str], list[str]]:
    """Возвращает (не применённые миграции, применённые миграции, которых нет в коде)."""
    return [name for name in known if name not in applied], sorted(applied - set(known))


async def schema_state(conn: asyncpg.Connection) -> tuple[list[str], list[str]]:
    """Состояние схемы БД относительно кода: (не применено, неизвестно коду)."""
    if not await conn.fetchval("SELECT to_regclass('schema_migrations')"):
        raise RuntimeError("БД не инициализирована, выполните `code-crawler db init`")
    rows = await conn.fetch("SELECT name FROM schema_migrations")
    return diff_migrations(migration_names(), {row["name"] for row in rows})


async def begin_migration(conn: asyncpg.Connection, init: bool = False) -> list[str]:
    """Берёт блокировку миграции и возвращает недостающие миграции по порядку.

    С `init=True` сначала создаёт таблицу учёта миграций, если её нет.
    """
    # Блокировка сессионная: держится, пока открыто соединение,
    # и не даёт двум миграциям идти сразу.
    await conn.execute("SELECT pg_advisory_lock($1)", _MIGRATION_LOCK)
    if init:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
    pending, unknown = await schema_state(conn)
    if unknown:
        raise RuntimeError(f"БД новее кода, неизвестные миграции: {', '.join(unknown)}")
    return pending


async def apply_migration(conn: asyncpg.Connection, name: str) -> None:
    # Одна транзакция с записью о миграции: сбой не оставляет её применённой наполовину.
    try:
        async with conn.transaction():
            await conn.execute((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
            await conn.execute("INSERT INTO schema_migrations (name) VALUES ($1)", name)
    except asyncpg.PostgresError as exc:
        raise RuntimeError(f"{name}: {exc}") from exc
