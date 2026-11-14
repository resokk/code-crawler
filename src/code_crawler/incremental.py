"""File fingerprints, dependency invalidation and incremental UCM snapshots."""

import asyncio
import errno
import hashlib
import json
import os
import re
import stat
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

import asyncpg
from pydantic import model_validator

from code_crawler import repos, snapshots
from code_crawler.ingestion import UcmBatch, _ingest_records, recheck, tick
from code_crawler.publication import load_snapshot_batch
from code_crawler.source_routing import source_language, valid_suffix
from code_crawler.ucm import (
    ContractModel,
    Entity,
    EntityType,
    SourceFile,
    Text,
    logical_id,
)


def _path(path: str) -> None:
    if (
        not path.strip()
        or any(p in ("", ".", "..") for p in path.split("/"))
        or any(c in path for c in ("\\", "\0", ":"))
    ):
        raise ValueError("file path must be canonical and repository-relative")


class FileAnalysis(ContractModel):
    path: Text
    entities: tuple[Entity, ...] = ()
    dependencies: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def valid_file(self) -> "FileAnalysis":
        _path(self.path)
        for dependency in self.dependencies:
            _path(dependency)
        if any(isinstance(entity, SourceFile) for entity in self.entities):
            raise ValueError("SourceFile is supplied by the orchestrator")
        return self


@dataclass(frozen=True)
class SourceInput:
    file: SourceFile
    content: bytes


@dataclass(frozen=True)
class IncrementalPlan:
    added: tuple[str, ...]
    changed: tuple[str, ...]
    deleted: tuple[str, ...]
    reanalyze: tuple[str, ...]
    reused: tuple[str, ...]
    git_changed: tuple[str, ...]
    full_rebuild: bool


@dataclass(frozen=True)
class IncrementalResult:
    snapshot_id: UUID
    base_snapshot_id: UUID | None
    plan: IncrementalPlan


@dataclass(frozen=True)
class _Worktree:
    commit: str
    branch: str | None
    dirty: bool
    sources: tuple[SourceInput, ...]
    fingerprint: str


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _scan(
    root: Path, paths: list[str], repository_id: UUID, languages: Mapping[str, str]
) -> tuple[SourceInput, ...]:
    result = []
    for path in sorted(set(paths)):
        _path(path)
        try:
            with ExitStack() as stack:
                directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                stack.callback(os.close, directory)
                parts = path.split("/")
                for part in parts[:-1]:
                    directory = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory,
                    )
                    stack.callback(os.close, directory)
                fd = os.open(
                    parts[-1],
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory,
                )
                stream = stack.enter_context(os.fdopen(fd, "rb"))
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    continue
                content = stream.read()
                after = os.fstat(stream.fileno())
        except OSError as exc:
            if exc.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
                continue
            raise
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("source changed during read")
        source = SourceFile(
            repository_id=str(repository_id),
            logical_key=path,
            id=logical_id(str(repository_id), EntityType.SOURCE_FILE, path),
            name=PurePosixPath(path).name,
            path=path,
            language=source_language(path, languages) or "unknown",
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        result.append(SourceInput(source, content))
    return tuple(result)


async def _capture(
    root: Path, repository_id: UUID, languages: Mapping[str, str]
) -> _Worktree:
    commit, branch = await repos.head(root)
    if await repos.git_output("ls-files", "--unmerged", "-z", cwd=root):
        raise ValueError("unresolved Git index conflicts")
    listing = await repos.git_output("ls-files", "--stage", "-z", cwd=root)
    paths = []
    for record in listing.split(b"\0"):
        if record:
            metadata, path = record.split(b"\t", 1)
            if metadata.split()[0] in (b"100644", b"100755"):
                paths.append(path.decode("utf-8"))
    sources = await asyncio.to_thread(_scan, root, paths, repository_id, languages)
    dirty = bool(
        await repos.git_output(
            "status", "--porcelain=v1", "-z", "--untracked-files=no", cwd=root
        )
    )
    if await repos.head(root) != (commit, branch):
        raise ValueError("HEAD changed during source capture")
    fingerprint = _hash(
        [[s.file.path, s.file.content_sha256, s.file.language] for s in sources]
    )
    return _Worktree(commit, branch, dirty, sources, fingerprint)


def plan_changes(
    previous: Mapping[str, SourceFile],
    current: Mapping[str, SourceFile],
    dependencies: set[tuple[str, str]],
    *,
    parsed_paths: set[str],
    full_rebuild: bool,
    git_changed: tuple[str, ...] = (),
) -> IncrementalPlan:
    """Plan reverse transitive invalidation from authoritative file fingerprints."""
    added = current.keys() - previous.keys()
    deleted = previous.keys() - current.keys()
    changed = {
        path
        for path in current.keys() & previous.keys()
        if (current[path].content_sha256, current[path].language)
        != (previous[path].content_sha256, previous[path].language)
    }
    reverse: dict[str, set[str]] = defaultdict(set)
    for dependent, dependency in dependencies:
        reverse[dependency].add(dependent)
    affected = set(added) | set(changed) | set(deleted)
    pending = deque(affected)
    while pending:
        for dependent in reverse[pending.popleft()]:
            if dependent not in affected:
                affected.add(dependent)
                pending.append(dependent)
    selected = parsed_paths if full_rebuild else parsed_paths & affected
    return IncrementalPlan(
        tuple(sorted(added)),
        tuple(sorted(changed)),
        tuple(sorted(deleted)),
        tuple(sorted(selected)),
        tuple(sorted(parsed_paths - selected)),
        tuple(sorted(set(git_changed))),
        full_rebuild,
    )


def _references(value: object, field: str = "") -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(_references(child, key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            result.update(_references(child, field))
    elif isinstance(value, str) and (field == "id" or field.endswith(("_id", "_ids"))):
        result.add(value)
    return result


def _assemble(
    repository_id: UUID,
    captured: _Worktree,
    baseline: UcmBatch | None,
    ownership: dict[str, str],
    dependencies: set[tuple[str, str]],
    plan: IncrementalPlan,
    analyses: tuple[FileAnalysis, ...],
) -> tuple[UcmBatch, dict[str, str], set[tuple[str, str]]]:
    for analysis in analyses:
        recheck(analysis)
        tick("Сборка снимка", len(analyses))
    if len({a.path for a in analyses}) != len(analyses) or {
        a.path for a in analyses
    } != set(plan.reanalyze):
        raise ValueError("analyzer must return each requested file exactly once")
    current = {s.file.path: s.file for s in captured.sources}
    entities = list(current.values())
    owners = {file.id: path for path, file in current.items()}
    reused = set(plan.reused)
    if baseline is not None and not plan.full_rebuild:
        for entity in baseline.entities:
            if not isinstance(entity, SourceFile) and ownership[entity.id] in reused:
                entities.append(entity)
                owners[entity.id] = ownership[entity.id]
    explicit = {(a, b) for a, b in dependencies if a in reused and a != b}
    for analysis in analyses:
        entities.extend(analysis.entities)
        for entity in analysis.entities:
            if entity.id in owners:
                raise ValueError("entity has multiple file owners")
            owners[entity.id] = analysis.path
        explicit.update(
            (analysis.path, path)
            for path in analysis.dependencies
            if path != analysis.path
        )
    tick("Проверка снимка")
    batch = UcmBatch(repository_id=repository_id, entities=tuple(entities))
    for entity in batch.entities:
        for target in _references(entity.model_dump(mode="json")):
            if target in owners and owners[target] != owners[entity.id]:
                explicit.add((owners[entity.id], owners[target]))
    return batch, owners, explicit


async def index_incremental(
    conn: asyncpg.Connection,
    repository_id: UUID,
    root: Path,
    analyze: Callable[[tuple[SourceInput, ...]], Awaitable[tuple[FileAnalysis, ...]]],
    *,
    languages: Mapping[str, str],
    analysis_version: str,
) -> IncrementalResult:
    """Analyze changed/dependent files, reusing the published UCM facts of other files."""
    if conn.is_in_transaction():
        raise ValueError("incremental indexing requires a free connection")
    required_version = getattr(analyze, "analysis_version", analysis_version)
    if required_version != analysis_version:
        raise ValueError("analysis_version must match the analyzer catalog profile")
    languages = dict(languages)
    if not analysis_version.strip() or any(
        not valid_suffix(key) or not value.strip() or value == "unknown"
        for key, value in languages.items()
    ):
        raise ValueError("invalid analysis version or language mapping")
    if not await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM public.ucm_repositories WHERE id=$1)",
        repository_id,
    ):
        raise ValueError("repository does not exist")
    root = await asyncio.to_thread(root.resolve, strict=True)
    git_root = Path(await repos.git("rev-parse", "--show-toplevel", cwd=root))
    if await asyncio.to_thread(git_root.resolve) != root:
        raise ValueError("root must be the Git repository root")
    captured = await _capture(root, repository_id, languages)
    profile_hash = _hash([analysis_version, sorted(languages.items())])
    published = await snapshots.published_snapshot(conn, repository_id)
    base_id = published["id"] if published else None
    baseline = await load_snapshot_batch(conn, base_id) if base_id else None
    ownership: dict[str, str] = {}
    dependencies: set[tuple[str, str]] = set()
    profile = None
    git_changed: tuple[str, ...] = ()
    if base_id:
        profile = await conn.fetchrow(
            "SELECT * FROM public.ingest_snapshot_profiles WHERE snapshot_id=$1",
            base_id,
        )
        if profile:
            ownership = {
                r["entity_id"]: r["path"]
                for r in await conn.fetch(
                    "SELECT path,entity_id FROM public.ingest_file_entities WHERE snapshot_id=$1",
                    base_id,
                )
            }
            if set(ownership) != {e.id for e in baseline.entities}:
                raise ValueError("baseline ownership manifest is incomplete")
            files = {e.path: e for e in baseline.entities if isinstance(e, SourceFile)}
            if any(path not in files for path in ownership.values()) or any(
                ownership[file.id] != path for path, file in files.items()
            ):
                raise ValueError("baseline file ownership is invalid")
            baseline_fingerprint = _hash(
                [
                    [path, file.content_sha256, file.language]
                    for path, file in sorted(files.items())
                ]
            )
            if baseline_fingerprint != published["source_fingerprint"]:
                raise ValueError(
                    "baseline source fingerprint does not match file manifest"
                )
            dependencies = {
                (r["dependent_path"], r["dependency_path"])
                for r in await conn.fetch(
                    "SELECT dependent_path,dependency_path FROM public.ingest_file_dependencies WHERE snapshot_id=$1",
                    base_id,
                )
            }
        try:
            base_commit = (
                (
                    await repos.git_output(
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        published["commit_hash"] + "^{commit}",
                        cwd=root,
                    )
                )
                .decode()
                .strip()
            )
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base_commit):
                raise RuntimeError("invalid base commit")
            diff = await repos.git_output(
                "diff",
                "--name-only",
                "-z",
                "--no-renames",
                base_commit,
                captured.commit,
                "--",
                cwd=root,
            )
            git_changed = tuple(
                path.decode("utf-8") for path in diff.split(b"\0") if path
            )
        except RuntimeError:
            # Fingerprints remain authoritative after history rewrite or shallow clone.
            git_changed = ()
    previous = (
        {e.path: e for e in baseline.entities if isinstance(e, SourceFile)}
        if baseline
        else {}
    )
    current = {s.file.path: s.file for s in captured.sources}
    parsed = {path for path in current if source_language(path, languages) is not None}
    plan = plan_changes(
        previous,
        current,
        dependencies,
        parsed_paths=parsed,
        full_rebuild=profile is None
        or profile["analysis_version"] != analysis_version
        or profile["profile_sha256"] != profile_hash,
        git_changed=git_changed,
    )
    selected_paths = set(plan.reanalyze)
    selected = tuple(s for s in captured.sources if s.file.path in selected_paths)
    analyses = await analyze(selected) if selected else ()
    batch, owners, dependency_pairs = await asyncio.to_thread(
        _assemble,
        repository_id,
        captured,
        baseline,
        ownership,
        dependencies,
        plan,
        analyses,
    )
    checked = await _capture(root, repository_id, languages)
    if (captured.commit, captured.branch, captured.dirty, captured.fingerprint) != (
        checked.commit,
        checked.branch,
        checked.dirty,
        checked.fingerprint,
    ):
        raise ValueError("worktree changed during analysis")
    snap = await snapshots.create_snapshot(
        conn,
        repository_id,
        snapshots.SnapshotInput(
            commit_hash=captured.commit,
            branch=captured.branch,
            source_fingerprint=captured.fingerprint,
            dirty=captured.dirty,
        ),
    )
    async with conn.transaction():
        await _ingest_records(conn, snap, batch)
        await conn.execute(
            "INSERT INTO public.ingest_snapshot_profiles(snapshot_id,analysis_version,profile_sha256) VALUES ($1,$2,$3)",
            snap,
            analysis_version,
            profile_hash,
        )
        await conn.copy_records_to_table(
            "ingest_file_entities",
            schema_name="public",
            columns=("snapshot_id", "path", "entity_id"),
            records=[(snap, path, entity_id) for entity_id, path in owners.items()],
        )
        await conn.copy_records_to_table(
            "ingest_file_dependencies",
            schema_name="public",
            columns=("snapshot_id", "dependent_path", "dependency_path"),
            records=[(snap, a, b) for a, b in sorted(dependency_pairs)],
        )
    return IncrementalResult(snap, base_id, plan)
