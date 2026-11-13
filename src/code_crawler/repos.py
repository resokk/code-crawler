"""Рабочие копии репозиториев: клонирование, имя, ветка и коммит."""

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path

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


async def git(*args: str, cwd: Path | None = None) -> str:
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
    return stdout.decode(errors="replace").strip()


async def sync(repo: Repo) -> None:
    """Клонирует репозиторий или подтягивает изменения в уже существующий клон."""
    if (repo.path / ".git").exists():
        await git("pull", "--ff-only", cwd=repo.path)
    else:
        repo.path.parent.mkdir(parents=True, exist_ok=True)
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
