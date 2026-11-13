import argparse
import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

from code_crawler import datamodel, db, indexer, repos

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
            console.print(f"[red]✗[/] {escape(title)}: {escape(str(exc))}")
            raise SystemExit(1) from exc
    console.print(f"[green]✓[/] {escape(title)}")


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


async def index(source: str) -> None:
    with operation(f"Индексация {source}") as progress:
        repo = repos.resolve(source)
        conn = await db.connect()
        try:
            pending, unknown = await db.schema_state(conn)
            if pending or unknown:
                raise RuntimeError(
                    "схема БД не соответствует коду, см. `code-crawler db status`"
                )
            repo_id = await indexer.register(
                conn, repo.name, repo.source, str(repo.path)
            )
            if repo.remote:
                task = progress.add_task("Клонирование", total=None)
                await repos.sync(repo)
                progress.remove_task(task)
            commit, branch = await repos.head(repo.path)
            paths = [p for p in await repos.files(repo.path) if indexer.is_indexable(p)]
            task = progress.add_task("Разбор файлов", total=len(paths))
            # Разбор нагружает процессор; в потоке он не блокирует цикл событий.
            graph = await asyncio.to_thread(
                indexer.build, repo.path, paths, lambda: progress.advance(task)
            )
            task = progress.add_task("Запись в БД", total=None)
            await indexer.store(conn, repo_id, graph, commit, branch)
        finally:
            await conn.close()
        for path, error in graph.failed:
            progress.console.print(f"  [yellow]пропущен[/] {path}: {escape(error)}")
        progress.console.print(
            f"  {repo.name}: ветка {branch or '(нет)'}, коммит {commit[:12]}\n"
            f"  файлов {graph.count('file')}, классов {graph.count('class')}, "
            f"методов {graph.count('method')}, SQL-запросов {graph.count('sql_query')}, "
            f"таблиц {len({ref[2] for ref in graph.refs})}"
        )


async def schema_import() -> None:
    with operation("Импорт структуры БД") as progress:
        task = progress.add_task("Чтение структуры", total=None)
        source = await db.connect("SOURCE_DATABASE_URL")
        try:
            model = await datamodel.introspect(source)
        finally:
            await source.close()
        progress.remove_task(task)
        progress.add_task("Запись в БД", total=None)
        conn = await db.connect()
        try:
            await datamodel.store(conn, model)
        finally:
            await conn.close()
        progress.console.print(
            f"  таблиц и представлений {len(model.relations)}, "
            f"колонок {len(model.columns)}, внешних ключей {len(model.foreign_keys)}"
        )


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
    schema_commands = commands.add_parser(
        "schema", help="слой данных: структура прикладной БД"
    ).add_subparsers(metavar="действие", required=True)
    schema_commands.add_parser(
        "import", help="прочитать структуру прикладной БД и заменить ею слой данных"
    ).set_defaults(run=schema_import)
    index_parser = commands.add_parser(
        "index", help="построить или обновить индекс репозитория"
    )
    index_parser.add_argument("source", help="локальный каталог или URL репозитория")
    index_parser.set_defaults(run=index)
    args = vars(parser.parse_args())
    asyncio.run(args.pop("run")(**args))
