"""Рабочие копии репозиториев: клонирование, имя, ветка и коммит."""

import asyncio
import hashlib
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REPOS_DIR = Path.home() / ".code-crawler" / "repos"


@dataclass
class Repo:
    name: str
    source: str
    path: Path
    remote: bool


def resolve(source: str) -> Repo:
    """Определяет имя и рабочий каталог репозитория по локальному пути или URL."""
    local = Path(source).expanduser()
    if local.is_dir():
        local = local.resolve()
        return Repo(local.name, str(local), local, remote=False)
    name = re.split(r"[/:]", source.rstrip("/").removesuffix(".git").rstrip("/"))[-1]
    # Имя становится именем каталога, поэтому ничего, кроме простого имени, не допускается.
    if not re.fullmatch(r"[\w.-]+", name) or name in (".", ".."):
        raise RuntimeError(f"не удалось извлечь имя репозитория из {source!r}")
    return Repo(name, source, REPOS_DIR / name, remote=True)


def _remote_identity(source: str) -> str:
    if "://" not in source:
        return source
    url = urlsplit(source)
    host = url.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if url.port is not None:
        host += f":{url.port}"
    return urlunsplit((url.scheme, host, url.path, "", ""))


def resolve_canonical(source: str) -> tuple[Repo, str]:
    """Resolve a source with collision-free canonical identity and remote cache path."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be nonblank")
    local = Path(source).expanduser()
    if local.is_dir():
        repo = resolve(source)
        return repo, repo.source
    key = _remote_identity(source)
    repo = resolve(key)
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    repo = replace(
        repo, source=source, path=REPOS_DIR / f"{repo.name}-{digest}", remote=True
    )
    return repo, key


async def sync_canonical(repo: Repo) -> None:
    """Refuse an unrelated cached origin before syncing the canonical checkout."""
    if await asyncio.to_thread((repo.path / ".git").exists):
        origin = await git("config", "--get", "remote.origin.url", cwd=repo.path)
        if _remote_identity(origin) != _remote_identity(repo.source):
            raise ValueError("cached repository origin does not match requested source")
        if origin != repo.source:
            await git("remote", "set-url", "origin", repo.source, cwd=repo.path)
        await git("pull", "--ff-only", "origin", cwd=repo.path)
    else:
        await sync(repo)


async def git_output(*args: str, cwd: Path | None = None) -> bytes:
    """Git output without decoding or trimming, including NUL-separated paths."""
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # Без терминала git не должен зависать на вопросе о пароле.
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    stdout, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError(f"git {args[0]}: {stderr.decode(errors='replace').strip()}")
    return stdout


async def git(*args: str, cwd: Path | None = None) -> str:
    return (await git_output(*args, cwd=cwd)).decode(errors="replace").strip()


async def sync(repo: Repo) -> None:
    """Клонирует репозиторий или подтягивает изменения в уже существующий клон."""
    if (repo.path / ".git").exists():
        await git("pull", "--ff-only", cwd=repo.path)
    else:
        await asyncio.to_thread(repo.path.parent.mkdir, parents=True, exist_ok=True)
        await git("clone", "--", repo.source, str(repo.path))


async def head(path: Path) -> tuple[str, str | None]:
    """Хеш текущего коммита и ветка (None, если HEAD не на ветке)."""
    commit = await git("rev-parse", "HEAD", cwd=path)
    branch = await git("rev-parse", "--abbrev-ref", "HEAD", cwd=path)
    return commit, None if branch == "HEAD" else branch


async def files(path: Path) -> list[str]:
    """Файлы под контролем git, пути относительно каталога репозитория."""
    listing = await git("ls-files", "-z", cwd=path)
    return [name for name in listing.split("\0") if name]
