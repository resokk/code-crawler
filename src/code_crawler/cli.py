import argparse
import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from uuid import UUID

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
    jobs,
    legacy,
    publication,
    repos,
    snapshots,
    source_evidence,
)
from code_crawler.bpmn_adapter import BpmnSourceAdapter
from code_crawler.bpmn_bindings import BINDING_PROFILES
from code_crawler.database_resolution import ConnectionAssignment
from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.java_adapter import (
    JAVA_PROFILES,
    JavaSourceAdapter,
    java_adapter_catalog,
)
from code_crawler.javascript_adapter import (
    JavaScriptSourceAdapter,
    TypeScriptSourceAdapter,
)
from code_crawler.kotlin_adapter import KotlinSourceAdapter
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


async def index(
    source: str,
    backend: str = "ucm",
    repository_key: str | None = None,
    java_profile: str | None = None,
    dialect: str | None = None,
    naming_policy: str | None = None,
    connections: str | None = None,
    bpmn_profile: str | None = None,
) -> None:
    """Build and publish canonical UCM by default; legacy requires explicit selection."""
    if backend == "legacy":
        if any(
            value is not None
            for value in (
                repository_key,
                java_profile,
                bpmn_profile,
                dialect,
                naming_policy,
                connections,
            )
        ):
            raise SystemExit("canonical options cannot be used with --backend legacy")
        await index_legacy(source)
        return
    if backend != "ucm":
        raise SystemExit("unknown index backend")
    with operation("Подготовка canonical репозитория"):
        if repository_key is not None and not repository_key.strip():
            raise ValueError("repository key must be nonblank")
        repo, default_key = await asyncio.to_thread(repos.resolve_canonical, source)
        if repo.remote:
            await repos.sync_canonical(repo)
        key = repository_key if repository_key is not None else default_key
        console.print(f"Canonical repository key: {escape(key)}")
    await index_registered(
        str(repo.path),
        key,
        java_profile if java_profile is not None else "orm",
        dialect if dialect is not None else "postgres",
        naming_policy if naming_policy is not None else "UNKNOWN",
        connections,
        publish=True,
        bpmn_profile=bpmn_profile or "auto",
    )


async def index_legacy(source: str) -> None:
    with operation(f"Индексация {source}") as progress:
        console.print(
            "[yellow]LEGACY compatibility: executes means SQL discovery, not verified execution.[/]"
        )
        repo = await asyncio.to_thread(repos.resolve, source)
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
                    KotlinSourceAdapter().descriptor,
                    PlplusSourceAdapter().descriptor,
                    BpmnSourceAdapter().descriptor,
                    JavaScriptSourceAdapter().descriptor,
                    TypeScriptSourceAdapter().descriptor,
                )
            ],
            ensure_ascii=False,
        )
    )


async def _snapshot_report(conn, snapshot_id: UUID) -> None:
    row = await conn.fetchrow(
        "SELECT s.id AS snapshot_id, s.repository_id, s.state AS status, s.commit_hash, s.source_fingerprint, s.dirty, "
        "(SELECT count(*) FROM public.ucm_entities e WHERE e.snapshot_id=s.id) AS entity_count, "
        "p.snapshot_id AS published_snapshot_id FROM public.ucm_snapshots s "
        "LEFT JOIN public.ucm_repository_publications p ON p.repository_id=s.repository_id "
        "WHERE s.id=$1",
        snapshot_id,
    )
    if row is None:
        raise ValueError("snapshot does not exist")
    diagnostics = await conn.fetch(
        "SELECT severity,count(*) AS count FROM public.ucm_source_diagnostics "
        "WHERE snapshot_id=$1 GROUP BY severity ORDER BY severity",
        snapshot_id,
    )
    report = dict(row)
    report["source_evidence"] = await source_evidence.evidence_status(conn, snapshot_id)
    report["diagnostics"] = {r["severity"]: r["count"] for r in diagnostics}
    console.print_json(json.dumps(report, default=str))


async def _publish_cli_snapshot(
    conn, snapshot_id: UUID, expected_current: UUID | None
) -> None:
    row = await conn.fetchrow(
        "SELECT repository_id,state FROM public.ucm_snapshots WHERE id=$1",
        snapshot_id,
    )
    if row is None:
        raise ValueError("snapshot does not exist")
    if row["state"] != "PUBLISHED":
        await publication.validate_snapshot(conn, snapshot_id)
    await publication.publish_snapshot(
        conn, row["repository_id"], snapshot_id, expected_snapshot_id=expected_current
    )


async def snapshot_validate(snapshot_id: UUID) -> None:
    """Validate stored canonical facts without changing publication visibility."""
    with operation("Проверка UCM snapshot"):
        conn = await db.connect()
        try:
            await publication.validate_snapshot(conn, snapshot_id)
            await _snapshot_report(conn, snapshot_id)
        finally:
            await conn.close()


async def snapshot_publish(snapshot_id: UUID, expected_current: UUID | None) -> None:
    """Validate and atomically publish using an explicitly supplied expected pointer."""
    with operation("Публикация UCM snapshot"):
        conn = await db.connect()
        try:
            await _publish_cli_snapshot(conn, snapshot_id, expected_current)
            await _snapshot_report(conn, snapshot_id)
        finally:
            await conn.close()


async def jobs_list() -> None:
    """Show the most recent ingest jobs with stage, attempt and failure diagnostics."""
    conn = await db.connect()
    try:
        rows = await conn.fetch(
            "SELECT j.id, r.repository_key, j.state, j.stage, j.attempt, j.snapshot_id, "
            "j.failure, j.updated_at FROM public.ingest_jobs j "
            "JOIN public.ucm_repositories r ON r.id=j.repository_id "
            "ORDER BY j.updated_at DESC LIMIT 50"
        )
    finally:
        await conn.close()
    console.print_json(
        json.dumps(
            [
                {**row, "failure": row["failure"] and json.loads(row["failure"])}
                for row in map(dict, rows)
            ],
            default=str,
        )
    )


async def jobs_retry(job_id: UUID) -> None:
    """Run the next attempt of a failed or abandoned ingest job with its parameters."""
    conn = await db.connect()
    try:
        # Блокировка задания живёт в этом соединении до конца повтора.
        try:
            parameters = await jobs.claim(conn, job_id)
        except ValueError as error:
            console.print(f"[red]✗[/] Повтор задания: {escape(str(error))}")
            raise SystemExit(1) from error
        await index_registered(**parameters, job_id=job_id)
    finally:
        await conn.close()


async def snapshot_gc(
    building_older_than: float | None, keep_retired: int | None
) -> None:
    """Delete abandoned BUILDING snapshots and RETIRED ones beyond the kept count."""
    if building_older_than is None and keep_retired is None:
        raise SystemExit("укажите --building-older-than и/или --keep-retired")
    with operation("Очистка UCM snapshots"):
        conn = await db.connect()
        try:
            result = await jobs.collect_garbage(
                conn,
                building_older_than_hours=building_older_than,
                keep_retired=keep_retired,
            )
        finally:
            await conn.close()
        console.print_json(json.dumps(result, default=str))


def _expected_pointer(value: str) -> UUID | None:
    if value == "none":
        return None
    try:
        return UUID(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected UUID or 'none'") from error


async def index_registered(
    root: str,
    repository_key: str,
    java_profile: str,
    dialect: str,
    naming_policy: str,
    connections: str | None = None,
    publish: bool = False,
    job_id: UUID | None = None,
    bpmn_profile: str = "auto",
) -> None:
    parameters = {
        "root": root,
        "repository_key": repository_key,
        "java_profile": java_profile,
        "bpmn_profile": bpmn_profile,
        "dialect": dialect,
        "naming_policy": naming_policy,
        "connections": connections,
        "publish": publish,
    }
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
            pending, unknown = await db.schema_state(conn)
            if pending or unknown:
                raise RuntimeError(
                    "схема БД не соответствует коду, см. `code-crawler db status`"
                )
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
                (
                    adapter,
                    GroovySourceAdapter(dialect=dialect),
                    PlplusSourceAdapter(),
                    BpmnSourceAdapter(profile=bpmn_profile),
                    KotlinSourceAdapter(),
                    JavaScriptSourceAdapter(),
                    TypeScriptSourceAdapter(),
                )
            )
            repository = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key=repository_key,
                    display_name=repository_key,
                    source=str(path),
                ),
            )
            if job_id is None:
                job_id = await jobs.begin(conn, repository, parameters)
            console.print(f"Ingest job: {job_id}")
            try:
                result = await index_sources(conn, repository, path, registry)
                console.print(f"BUILDING snapshot: {result.snapshot_id}")
                await jobs.advance(
                    conn, job_id, "PUBLISH" if publish else "INDEX", result.snapshot_id
                )
                if publish:
                    await _publish_cli_snapshot(
                        conn, result.snapshot_id, result.base_snapshot_id
                    )
            except Exception as error:
                # Сбой записи статуса не должен скрыть исходную ошибку; reap пометит позже.
                with suppress(Exception):
                    await jobs.finish(conn, job_id, error)
                raise
            await jobs.finish(conn, job_id)
            await _snapshot_report(conn, result.snapshot_id)
        finally:
            await conn.close()


def _canonical_options(parser: argparse.ArgumentParser, *, defaults: bool) -> None:
    parser.add_argument(
        "--bpmn-profile", choices=BINDING_PROFILES, default="auto" if defaults else None
    )
    parser.add_argument(
        "--java-profile", choices=JAVA_PROFILES, default="orm" if defaults else None
    )
    parser.add_argument(
        "--dialect",
        choices=("postgres", "mysql", "tsql"),
        default="postgres" if defaults else None,
    )
    parser.add_argument(
        "--naming-policy",
        choices=("UNKNOWN", "IDENTITY"),
        default="UNKNOWN" if defaults else None,
    )
    parser.add_argument("--connections", help="JSON list of typed ConnectionAssignment")


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
    _canonical_options(source_parser, defaults=True)
    source_parser.add_argument(
        "--publish",
        action="store_true",
        help="проверить и атомарно опубликовать snapshot",
    )
    source_parser.set_defaults(run=index_registered)
    snapshot_commands = commands.add_parser(
        "snapshot", help="проверка и публикация canonical UCM"
    ).add_subparsers(metavar="действие", required=True)
    validate_parser = snapshot_commands.add_parser(
        "validate", help="проверить snapshot и перевести в READY"
    )
    validate_parser.add_argument("snapshot_id", type=UUID)
    validate_parser.set_defaults(run=snapshot_validate)
    publish_parser = snapshot_commands.add_parser(
        "publish", help="проверить и опубликовать snapshot с CAS"
    )
    publish_parser.add_argument("snapshot_id", type=UUID)
    publish_parser.add_argument(
        "--expected-current", required=True, type=_expected_pointer, metavar="UUID|none"
    )
    publish_parser.set_defaults(run=snapshot_publish)
    gc_parser = snapshot_commands.add_parser(
        "gc", help="удалить брошенные BUILDING и старые RETIRED snapshots"
    )
    gc_parser.add_argument(
        "--building-older-than",
        type=float,
        metavar="ЧАСЫ",
        help="удалить BUILDING snapshots старше N часов без работающего задания",
    )
    gc_parser.add_argument(
        "--keep-retired",
        type=int,
        metavar="N",
        help="оставить N последних RETIRED snapshots на репозиторий, остальные удалить",
    )
    gc_parser.set_defaults(run=snapshot_gc)
    job_commands = commands.add_parser(
        "jobs", help="состояние и повтор заданий индексации"
    ).add_subparsers(metavar="действие", required=True)
    job_commands.add_parser("list", help="последние задания").set_defaults(
        run=jobs_list
    )
    retry_parser = job_commands.add_parser(
        "retry", help="повторить упавшее или брошенное задание"
    )
    retry_parser.add_argument("job_id", type=UUID)
    retry_parser.set_defaults(run=jobs_retry)
    index_parser = commands.add_parser(
        "index",
        help="построить, проверить и опубликовать canonical UCM (legacy — явно)",
    )
    index_parser.add_argument("source", help="локальный каталог или URL репозитория")
    index_parser.add_argument("--backend", choices=("ucm", "legacy"), default="ucm")
    index_parser.add_argument(
        "--repository-key", help="canonical key; по умолчанию source identity"
    )
    _canonical_options(index_parser, defaults=False)
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
