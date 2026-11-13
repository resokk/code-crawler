import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "source,code",
    [
        (b"class Broken { int x }", "MISSING_TOKEN"),
        (b"class Broken {\xff}", "INVALID_UTF8"),
    ],
)
def test_cli_persists_and_reports_parser_diagnostics(
    database_url: str, tmp_path: Path, source: bytes, code: str
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "Diagnostics Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            (tmp_path / "Broken.java").write_bytes(source)
            (tmp_path / "Good.java").write_text("class Good { void ok() {} }")
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "from code_crawler.cli import main; main()",
                "index",
                str(tmp_path),
                env={**os.environ, "DATABASE_URL": database_url, "NO_COLOR": "1"},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await asyncio.wait_for(process.communicate(), timeout=30)
            assert process.returncode == 0, output.decode()
            assert code in output.decode() and "Broken.java:1:" in output.decode()
            attrs = json.loads(
                await conn.fetchval(
                    "SELECT attrs FROM nodes WHERE kind='file' AND file_path='Broken.java'"
                )
            )
            assert attrs["source_sha256"] == hashlib.sha256(source).hexdigest()
            assert attrs["diagnostics"][0]["code"] == code
            assert attrs["parse_coverage"] == "PARTIAL"
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM nodes WHERE qualified_name='Good.ok'"
                )
                == 1
            )
        finally:
            await conn.close()

    asyncio.run(scenario())
