import asyncio
from uuid import UUID

import pytest

from code_crawler.incremental import SourceInput
from code_crawler.source_evidence import _slice, archive_sources
from code_crawler.ucm import EntityType, Position, SourceFile, SourceRange, logical_id

REPO = UUID("11111111-1111-1111-1111-111111111111")
FILE_ID = logical_id(str(REPO), EntityType.SOURCE_FILE, "A.java")


def location(start, end):
    return SourceRange(
        source_file_id=FILE_ID,
        start=Position(line=start[0], byte_column=start[1]),
        end=Position(line=end[0], byte_column=end[1]),
    )


@pytest.mark.parametrize(
    "content,start,end,expected",
    [
        (b"", (1, 0), (1, 0), b""),
        ("я\r\nβ\n".encode(), (1, 0), (2, 2), "я\r\nβ".encode()),
        (b"a\n", (2, 0), (2, 0), b""),
        ("aяb".encode(), (1, 1), (1, 3), "я".encode()),
        (b"a\r\nb", (1, 1), (2, 0), b"\r\n"),
    ],
)
def test_exact_utf8_crlf_and_eof_ranges(content, start, end, expected):
    assert _slice(content, location(start, end)) == expected


@pytest.mark.parametrize(
    "start,end",
    [
        ((1, 1), (1, 2)),
        ((1, 0), (1, 1)),
        ((1, 0), (2, 0)),
        ((1, 0), (1, 4)),
    ],
)
def test_non_boundaries_and_out_of_bounds_are_rejected(start, end):
    with pytest.raises(ValueError):
        _slice("я".encode(), location(start, end))


def test_archive_rejects_forged_bytes_before_database_access():
    file = SourceFile(
        repository_id=str(REPO),
        logical_key="A.java",
        id=FILE_ID,
        name="A.java",
        path="A.java",
        language="java",
        content_sha256="a" * 64,
    )
    with pytest.raises(ValueError, match="content_sha256"):
        asyncio.run(
            archive_sources(
                object(), REPO, (SourceInput(file, b"wrong"),), origin="PROVIDED_BYTES"
            )
        )
