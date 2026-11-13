import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from code_crawler import indexer, java


def test_valid_source_preserves_exact_utf8_crlf_declaration_ranges() -> None:
    source = "// я\r\nclass Пример { void run() {} }\r\n".encode()
    result = java.analyze(source)
    assert result.coverage == "COMPLETE" and result.diagnostics == ()
    assert result.source_sha256 == hashlib.sha256(source).hexdigest()
    assert result.byte_length == len(source)
    cls, method = result.symbols
    assert (
        source[cls.source_span.start_byte : cls.source_span.end_byte]
        == "class Пример { void run() {} }".encode()
    )
    assert (
        source[method.source_span.start_byte : method.source_span.end_byte]
        == b"void run() {}"
    )
    assert method.source_span.start.line == 2
    assert method.source_span.start.byte_column == len("class Пример { ".encode())
    assert java.parse(source) == result.symbols


def test_missing_unnamed_token_has_zero_width_location() -> None:
    source = b"class A { int x }"
    (diagnostic,) = java.analyze(source).diagnostics
    assert diagnostic.code == "MISSING_TOKEN" and diagnostic.node_type == ";"
    assert diagnostic.source_span.start_byte == diagnostic.source_span.end_byte == 15
    assert diagnostic.source_span.start == diagnostic.source_span.end


def test_error_after_unicode_uses_byte_columns() -> None:
    source = 'class A { String s="я"; int x = ; }'.encode()
    result = java.analyze(source)
    (diagnostic,) = result.diagnostics
    assert result.coverage == "PARTIAL"
    assert diagnostic.code == "SYNTAX_ERROR"
    assert (
        source[diagnostic.source_span.start_byte : diagnostic.source_span.end_byte]
        == b"="
    )
    assert diagnostic.source_span.start.byte_column == source.rindex(b"=")
    assert result == java.analyze(source)


def test_invalid_encoding_is_not_silently_replaced() -> None:
    source = b"// ok\r\nclass A {\xff}"
    result = java.analyze(source)
    (diagnostic,) = result.diagnostics
    assert result.symbols == [] and result.coverage == "PARTIAL"
    assert diagnostic.code == "INVALID_UTF8"
    assert diagnostic.source_span.start.line == 2
    assert diagnostic.source_span.start.byte_column == len(b"class A {")
    assert (
        source[diagnostic.source_span.start_byte : diagnostic.source_span.end_byte]
        == b"\xff"
    )


@pytest.mark.parametrize(
    "source",
    [
        b"class { }",
        b"class A { void () {} }",
        b"class A { int = ; }",
        b"class A { void m( { }",
    ],
)
def test_recovered_ast_does_not_fabricate_empty_symbols(source: bytes) -> None:
    result = java.analyze(source)
    assert result.diagnostics and result.coverage == "PARTIAL"
    assert all(symbol.name for symbol in result.symbols)


def test_concurrent_parses_keep_provenance_separate() -> None:
    sources = [f"class A{i} {{ void m() {{}} }}".encode() for i in range(24)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(java.analyze, sources))
    for i, (source, result) in enumerate(zip(sources, results, strict=True)):
        assert result.symbols[0].qualified_name == f"A{i}"
        assert result.source_sha256 == hashlib.sha256(source).hexdigest()
        assert result.diagnostics == ()


def test_mutable_input_is_rejected() -> None:
    with pytest.raises(TypeError, match="immutable bytes"):
        java.analyze(bytearray(b"class A {}"))


def test_indexer_retains_diagnostics_and_neighbouring_valid_symbols(
    tmp_path: Path,
) -> None:
    broken = b"class Broken { int x }"
    (tmp_path / "Broken.java").write_bytes(broken)
    (tmp_path / "Good.java").write_text("class Good { void ok() {} }")
    graph = indexer.build(tmp_path, ["Broken.java", "Good.java"], lambda: None)
    assert graph.failed == []
    attrs = next(n[6] for n in graph.nodes if n[0] == "file" and n[3] == "Broken.java")
    assert attrs["parse_coverage"] == "PARTIAL"
    assert attrs["source_sha256"] == hashlib.sha256(broken).hexdigest()
    assert attrs["diagnostics"][0]["code"] == "MISSING_TOKEN"
    assert "Good.ok" in {n[2] for n in graph.nodes}


def test_file_changed_during_read_is_not_indexed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changing = tmp_path / "Changing.java"
    changing.write_text("class Old {}")
    (tmp_path / "Good.java").write_text("class Good {}")
    original = Path.read_bytes

    def read_and_change(path: Path) -> bytes:
        content = original(path)
        if path == changing:
            path.write_text("class ChangedAndLonger {}")
        return content

    monkeypatch.setattr(Path, "read_bytes", read_and_change)
    graph = indexer.build(tmp_path, ["Changing.java", "Good.java"], lambda: None)
    assert graph.failed == [
        ("Changing.java", "RuntimeError: source changed during read")
    ]
    assert {node[2] for node in graph.nodes} == {"Good.java", "Good"}
