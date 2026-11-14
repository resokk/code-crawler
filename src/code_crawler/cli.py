import argparse
import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import TypeAdapter
from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, TaskID, TimeElapsedColumn

from code_crawler import (
    database_schema,
    datamodel,
    db,
    indexer,
    ingestion,
    legacy,
    repos,
    snapshots,
)
from code_crawler.database_resolution import ConnectionAssignment
from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.java_adapter import (
    JAVA_PROFILES,
    JavaSourceAdapter,
    java_adapter_catalog,
)
from code_crawler.plplus_adapter import PlplusSourceAdapter
from code_crawler.source_adapters import AdapterRegistry, index_sources

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
        for node in graph.nodes:
            if node[0] == "file":
                for diagnostic in node[6].get("diagnostics", []):
                    position = diagnostic["source_span"]["start"]
                    console.print(
                        escape(
                            f"  {node[3]}:{position['line']}:{position['byte_column']}: {diagnostic['code']} — {diagnostic['message']}"
                        )
                    )
        progress.console.print(
            f"  {repo.name}: ветка {branch or '(нет)'}, коммит {commit[:12]}\n"
            f"  файлов {graph.count('file')}, классов {graph.count('class')}, "
            f"методов {graph.count('method')}, SQL-запросов {graph.count('sql_query')}, "
            f"таблиц {len({ref[2] for ref in graph.refs})}"
        )


async def migrate_index(legacy_name: str, repository_key: str) -> None:
    with operation("Миграция legacy индекса"):
        conn = await db.connect()
        try:
            snapshot = await legacy.migrate_index(conn, legacy_name, repository_key)
            console.print(f"snapshot: {snapshot}")
        finally:
            await conn.close()


async def compare_index(repository_key: str) -> None:
    with operation("Сравнение индексов"):
        conn = await db.connect()
        try:
            report = await legacy.compare_index(conn, repository_key)
            console.print_json(json.dumps(report, ensure_ascii=False))
            if not report["matches"]:
                raise ValueError("индексы различаются")
        finally:
            await conn.close()


async def use_index(repository_key: str, backend: str) -> None:
    with operation("Переключение чтения"):
        conn = await db.connect()
        try:
            await legacy.use_index(conn, repository_key, backend)
        finally:
            await conn.close()


async def show_index(repository_key: str) -> None:
    with operation("Чтение индекса"):
        conn = await db.connect()
        try:
            graph = await legacy.read_graph(conn, repository_key)
            console.print_json(
                json.dumps(
                    {"nodes": graph.nodes, "edges": graph.edges, "refs": graph.refs},
                    ensure_ascii=False,
                )
            )
        finally:
            await conn.close()


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


async def schema_import_version(database_key: str, version_key: str) -> None:
    with operation("Импорт версии структуры БД"):
        source = await db.connect("SOURCE_DATABASE_URL")
        try:
            document = await database_schema.introspect_schema(
                source, database_key, version_key
            )
        finally:
            await source.close()
        conn = await db.connect()
        try:
            fingerprint = await database_schema.import_schema(conn, document)
            console.print(f"{database_key}/{version_key}: {fingerprint}")
        finally:
            await conn.close()


async def schema_import_manifest(path: str) -> None:
    with operation("Импорт schema manifest"):
        content = await asyncio.to_thread(Path(path).read_bytes)
        document = await asyncio.to_thread(
            database_schema.SchemaImport.model_validate_json, content
        )
        conn = await db.connect()
        try:
            fingerprint = await database_schema.import_schema(conn, document)
            console.print(
                f"{document.database_key}/{document.version_key}: {fingerprint}"
            )
        finally:
            await conn.close()


async def list_adapters() -> None:
    console.print_json(
        json.dumps(
            [
                descriptor.manifest()
                for descriptor in (
                    *java_adapter_catalog(),
                    GroovySourceAdapter().descriptor,
                    PlplusSourceAdapter().descriptor,
                )
            ],
            ensure_ascii=False,
        )
    )


async def index_registered(
    root: str,
    repository_key: str,
    java_profile: str,
    dialect: str,
    naming_policy: str,
    connections: str | None = None,
) -> None:
    with operation("Индексация source adapters") as progress:
        tasks: dict[str, TaskID] = {}

        def advance(stage: str, total: int | None) -> None:
            if stage not in tasks:
                # Несчётный этап заканчивается с началом следующего — иначе его часы идут дальше.
                for task in progress.tasks[1:]:
                    if task.total is None:
                        progress.update(task.id, total=1, completed=1)
                tasks[stage] = progress.add_task(stage, total=total)
            if total is not None:
                progress.advance(tasks[stage])

        ingestion.progress.set(advance)
        path = await asyncio.to_thread(Path(root).resolve, strict=True)
        assignments = ()
        if connections is not None:
            content = await asyncio.to_thread(Path(connections).read_bytes)
            assignments = await asyncio.to_thread(
                TypeAdapter(tuple[ConnectionAssignment, ...]).validate_json, content
            )
        conn = await db.connect()
        try:
            schemas = []
            for key, version in sorted(
                {(a.context.database_key, a.context.version_key) for a in assignments}
            ):
                schemas.append(await database_schema.load_schema(conn, key, version))
            adapter = JavaSourceAdapter(
                profile=java_profile,
                schemas=tuple(schemas),
                assignments=assignments,
                dialect=dialect,
                naming_policy=naming_policy,
            )
            registry = AdapterRegistry(
                (adapter, GroovySourceAdapter(dialect=dialect), PlplusSourceAdapter())
            )
            repository = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key=repository_key,
                    display_name=repository_key,
                    source=str(path),
                ),
            )
            result = await index_sources(conn, repository, path, registry)
            console.print(f"BUILDING snapshot: {result.snapshot_id}")
        finally:
            await conn.close()


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
    version_parser = schema_commands.add_parser(
        "import-version",
        help="импортировать неизменяемую версию из SOURCE_DATABASE_URL",
    )
    version_parser.add_argument("--database-key", required=True)
    version_parser.add_argument("--version-key", required=True)
    version_parser.set_defaults(run=schema_import_version)
    manifest_parser = schema_commands.add_parser(
        "import-manifest", help="импортировать typed JSON schema manifest"
    )
    manifest_parser.add_argument("path")
    manifest_parser.set_defaults(run=schema_import_manifest)
    adapter_commands = commands.add_parser(
        "adapters", help="versioned source adapter capabilities"
    ).add_subparsers(metavar="действие", required=True)
    adapter_commands.add_parser(
        "list",
        help="описать доступные Java profiles, Groovy и PL/Plus adapters без доступа к БД",
    ).set_defaults(run=list_adapters)
    source_parser = commands.add_parser(
        "index-sources",
        help="построить canonical BUILDING snapshot через source registry",
    )
    source_parser.add_argument("root")
    source_parser.add_argument("--repository-key", required=True)
    source_parser.add_argument("--java-profile", choices=JAVA_PROFILES, default="orm")
    source_parser.add_argument(
        "--dialect", choices=("postgres", "mysql", "tsql"), default="postgres"
    )
    source_parser.add_argument(
        "--naming-policy", choices=("UNKNOWN", "IDENTITY"), default="UNKNOWN"
    )
    source_parser.add_argument(
        "--connections", help="JSON tuple/list of typed ConnectionAssignment"
    )
    source_parser.set_defaults(run=index_registered)
    index_parser = commands.add_parser(
        "index", help="построить или обновить индекс репозитория"
    )
    index_parser.add_argument("source", help="локальный каталог или URL репозитория")
    index_parser.set_defaults(run=index)
    migrate_parser = commands.add_parser(
        "migrate-index", help="перенести legacy индекс в UCM snapshot"
    )
    migrate_parser.add_argument("legacy_name")
    migrate_parser.add_argument("--repository-key", required=True)
    migrate_parser.set_defaults(run=migrate_index)
    for name, run in (
        ("compare-index", compare_index),
        ("use-index", use_index),
        ("show-index", show_index),
    ):
        command = commands.add_parser(name)
        command.add_argument("repository_key")
        if name == "use-index":
            command.add_argument("--backend", choices=("legacy", "ucm"), required=True)
        command.set_defaults(run=run)
    args = vars(parser.parse_args())
    asyncio.run(args.pop("run")(**args))
