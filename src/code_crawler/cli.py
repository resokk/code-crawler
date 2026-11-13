import argparse
import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

from code_crawler import db

console = Console()


@contextmanager
def operation(title: str) -> Iterator[Progress]:
    """Обёртка любой операции CLI: живой прогресс во время работы и итоговый статус.

    Счётные шаги добавляются через `progress.add_task(..., total=n)`.
    """
    with Progress(
        SpinnerColumn(),
        *Progress.get_default_columns(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(title, total=None)
        try:
            yield progress
        except Exception as exc:
            progress.stop()
            console.print(f"[red]✗[/] {title}: {exc}")
            raise SystemExit(1) from exc
    console.print(f"[green]✓[/] {title}")


async def db_status() -> None:
    with operation("Состояние БД"):
        conn = await db.connect()
        try:
            pending, unknown = await db.schema_state(conn)
        finally:
            await conn.close()
        if unknown:
            raise RuntimeError(
                f"БД новее кода, неизвестные миграции: {', '.join(unknown)}"
            )
        if pending:
            raise RuntimeError(f"схема устарела, не применено: {', '.join(pending)}")


async def _migrate(title: str, init: bool) -> None:
    with operation(title) as progress:
        conn = await db.connect()
        try:
            pending = await db.begin_migration(conn, init=init)
            task = progress.add_task("Миграции", total=len(pending))
            for name in pending:
                await db.apply_migration(conn, name)
                progress.console.print(f"  применена {name}")
                progress.advance(task)
        finally:
            await conn.close()


async def db_init() -> None:
    await _migrate("Инициализация БД", init=True)


async def db_migrate() -> None:
    await _migrate("Миграция БД", init=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="code-crawler", description="Управление индексами code-crawler."
    )
    commands = parser.add_subparsers(metavar="команда", required=True)
    db_commands = commands.add_parser(
        "db", help="состояние, инициализация и миграции БД"
    ).add_subparsers(metavar="действие", required=True)
    db_commands.add_parser(
        "status", help="проверить, что схема БД соответствует коду"
    ).set_defaults(run=db_status)
    db_commands.add_parser(
        "init", help="подготовить пустую БД и применить все миграции"
    ).set_defaults(run=db_init)
    db_commands.add_parser(
        "migrate", help="применить недостающие миграции схемы БД"
    ).set_defaults(run=db_migrate)
    asyncio.run(parser.parse_args().run())
