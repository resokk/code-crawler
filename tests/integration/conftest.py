"""Opt-in PostgreSQL tests, each in a newly created disposable database."""

import asyncio
import os
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest


@pytest.fixture
def database_url() -> Iterator[str]:
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("set TEST_DATABASE_URL to a PostgreSQL 15 admin database")
    name = f"crawler_test_{uuid4().hex}"

    async def create() -> str:
        conn = await asyncpg.connect(admin_url)
        try:
            version = int(await conn.fetchval("SHOW server_version_num"))
            if not 150000 <= version < 160000:
                pytest.fail("integration suite requires PostgreSQL 15")
            await conn.execute(f'CREATE DATABASE "{name}"')
            return name
        finally:
            await conn.close()

    asyncio.run(create())
    parts = urlsplit(admin_url)
    target = urlunsplit(parts._replace(path=f"/{name}"))
    try:
        yield target
    finally:

        async def drop() -> None:
            conn = await asyncpg.connect(admin_url)
            try:
                await conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
            finally:
                await conn.close()

        asyncio.run(drop())
