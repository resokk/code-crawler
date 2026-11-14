import asyncio
import hashlib
from dataclasses import dataclass
from uuid import UUID

import pytest
from pydantic import ValidationError

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_adapter import (
    JAVA_PROFILES,
    JavaSourceAdapter,
    java_adapter_catalog,
)
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterError,
    AdapterFileResult,
    AdapterRegistry,
    SourceRoute,
)
from code_crawler.ucm import (
    CodeEntity,
    Coverage,
    EntityType,
    Position,
    SourceAnalysis,
    SourceDiagnostic,
    SourceFile,
    SourceRange,
    Symbol,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def source(path: str, text: str = "content", language: str = "test") -> SourceInput:
    content = text.encode()
    return SourceInput(
        SourceFile(
            repository_id=str(REPO),
            logical_key=path,
            id=logical_id(str(REPO), EntityType.SOURCE_FILE, path),
            name=path,
            path=path,
            language=language,
            content_sha256=hashlib.sha256(content).hexdigest(),
        ),
        content,
    )


def descriptor(
    key: str = "test", suffix: str = ".txt", version: str = "1"
) -> AdapterDescriptor:
    return AdapterDescriptor(
        key=key,
        version=version,
        routes=(SourceRoute(suffix=suffix, language="test"),),
        capabilities=(
            Coverage(
                capability="test.symbols", analyzer_version="1", status="COMPLETE"
            ),
        ),
        entity_types=(EntityType.SYMBOL,),
    )


@dataclass
class TestAdapter:
    __test__ = False
    descriptor: AdapterDescriptor
    mode: str = "normal"
    version: str = "test/1"

    async def prepare(self, sources: tuple[SourceInput, ...]):
        adapter = self

        class Prepared:
            analysis_version = adapter.version

            async def __call__(
                self, selected: tuple[SourceInput, ...]
            ) -> tuple[AdapterFileResult, ...]:
                results = []
                for src in selected:
                    symbol = Symbol(
                        repository_id=src.file.repository_id,
                        logical_key=src.file.path + ":symbol",
                        id=logical_id(
                            src.file.repository_id,
                            EntityType.SYMBOL,
                            src.file.path + ":symbol",
                        ),
                        name=src.file.path,
                        symbol_kind="CLASS",
                        qualified_name=src.file.path,
                    )
                    diagnostics = ()
                    capabilities = ()
                    entities = (symbol,)
                    if adapter.mode == "error":
                        diagnostics = (
                            SourceDiagnostic(
                                severity="ERROR",
                                code="parse.error",
                                message="recovered parser error",
                                source_range=SourceRange(
                                    source_file_id=src.file.id,
                                    start=Position(line=1, byte_column=0),
                                    end=Position(line=1, byte_column=1),
                                ),
                            ),
                        )
                    if adapter.mode == "out-of-range":
                        diagnostics = (
                            SourceDiagnostic(
                                severity="ERROR",
                                code="parse.error",
                                message="bad range",
                                source_range=SourceRange(
                                    source_file_id=src.file.id,
                                    start=Position(line=100, byte_column=0),
                                    end=Position(line=100, byte_column=1),
                                ),
                            ),
                        )
                    if adapter.mode == "unsupported":
                        capabilities = (
                            Coverage(
                                capability="test.symbols",
                                analyzer_version="1",
                                status="UNSUPPORTED",
                                reasons=("feature unsupported",),
                            ),
                        )
                        entities = ()
                    if adapter.mode == "undeclared":
                        key = src.file.path + ":candidate"
                        entities = (
                            CodeEntity(
                                repository_id=src.file.repository_id,
                                logical_key=key,
                                id=logical_id(
                                    src.file.repository_id,
                                    EntityType.SQL_CANDIDATE,
                                    key,
                                ),
                                name="candidate",
                                entity_type=EntityType.SQL_CANDIDATE,
                            ),
                        )
                    if adapter.mode == "fact-out-of-range":
                        entities = (
                            symbol.model_copy(
                                update={
                                    "source_range": SourceRange(
                                        source_file_id=src.file.id,
                                        start=Position(line=10, byte_column=0),
                                        end=Position(line=10, byte_column=1),
                                    )
                                }
                            ),
                        )
                    if adapter.mode == "coverage-version":
                        capabilities = (
                            Coverage(
                                capability="test.symbols",
                                analyzer_version="2",
                                status="COMPLETE",
                            ),
                        )
                    if adapter.mode == "descriptor-change":
                        adapter.descriptor = adapter.descriptor.model_copy(
                            update={"version": "changed"}
                        )
                    results.append(
                        AdapterFileResult(
                            analysis=FileAnalysis(
                                path=src.file.path, entities=entities
                            ),
                            diagnostics=diagnostics,
                            capabilities=capabilities,
                        )
                    )
                if adapter.mode == "missing":
                    return ()
                if adapter.mode == "duplicate":
                    return tuple(results + results)
                if adapter.mode == "version-change":
                    self.analysis_version = "changed"
                return tuple(results)

        return Prepared()


def run(registry: AdapterRegistry, sources: tuple[SourceInput, ...]):
    async def scenario():
        prepared = await registry.prepare(sources)
        return prepared, await prepared(sources)

    return asyncio.run(scenario())


def test_registry_routes_and_emits_typed_report() -> None:
    prepared, results = run(
        AdapterRegistry((TestAdapter(descriptor()),)), (source("A.txt"),)
    )
    assert prepared.analysis_version.startswith("source.registry/1:")
    report = next(e for e in results[0].entities if isinstance(e, SourceAnalysis))
    assert report.adapter_key == "test" and report.analysis_version == "test/1"
    assert report.capabilities[0].status == "COMPLETE"


def test_longest_suffix_wins_independently_of_adapter_order() -> None:
    first = TestAdapter(descriptor("base", ".ts"))
    second = TestAdapter(descriptor("declaration", ".d.ts"))
    for registry in (
        AdapterRegistry((first, second)),
        AdapterRegistry((second, first)),
    ):
        assert registry.route("nested/A.d.ts").key == "declaration"
        assert registry.route("A.ts").key == "base"
        assert registry.route("A.TS") is None
        assert registry.route("README.md") is None


def test_duplicate_keys_and_suffix_ownership_are_rejected() -> None:
    with pytest.raises(ValueError, match="key"):
        AdapterRegistry(
            (TestAdapter(descriptor()), TestAdapter(descriptor(suffix=".other")))
        )
    with pytest.raises(ValueError, match="suffix"):
        AdapterRegistry((TestAdapter(descriptor()), TestAdapter(descriptor("other"))))


def test_descriptor_order_does_not_change_fingerprint() -> None:
    first = TestAdapter(descriptor("base", ".txt"))
    second = TestAdapter(descriptor("other", ".spec"))

    async def profile(adapters):
        return (await AdapterRegistry(adapters).prepare(())).analysis_version

    assert asyncio.run(profile((first, second))) == asyncio.run(
        profile((second, first))
    )
    assert asyncio.run(profile((first,))) != asyncio.run(
        profile((TestAdapter(descriptor(version="2")),))
    )
    assert asyncio.run(profile((first,))) != asyncio.run(
        profile((TestAdapter(descriptor(), version="test/2"),))
    )


def test_invalid_routes_and_orchestrator_entities_are_rejected() -> None:
    for suffix in ("java", "..java", ".d..ts", "/a.java"):
        with pytest.raises(ValidationError):
            SourceRoute(suffix=suffix, language="java")
    with pytest.raises(ValidationError):
        SourceRoute(suffix=".java", language="unknown")
    with pytest.raises(ValidationError):
        AdapterDescriptor(
            **{
                **descriptor().model_dump(),
                "entity_types": (EntityType.SOURCE_ANALYSIS,),
            }
        )


def test_byte_hash_and_language_must_match_capture() -> None:
    src = source("A.txt")
    bad = SourceInput(src.file, b"other")
    with pytest.raises(ValueError, match="hash"):
        run(AdapterRegistry((TestAdapter(descriptor()),)), (bad,))
    with pytest.raises(ValueError, match="language"):
        run(
            AdapterRegistry((TestAdapter(descriptor()),)),
            (source("A.txt", language="other"),),
        )


def test_changed_or_unregistered_callback_sources_are_rejected() -> None:
    async def scenario():
        prepared = await AdapterRegistry((TestAdapter(descriptor()),)).prepare(
            (source("A.txt"), source("README.md", language="unknown"))
        )
        with pytest.raises(ValueError, match="differs"):
            await prepared((source("A.txt", "changed"),))
        with pytest.raises(ValueError, match="unregistered"):
            await prepared((source("README.md", language="unknown"),))

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode",
    [
        "missing",
        "duplicate",
        "version-change",
        "out-of-range",
        "undeclared",
        "fact-out-of-range",
        "coverage-version",
        "descriptor-change",
    ],
)
def test_invalid_adapter_results_fail_before_ingestion(mode: str) -> None:
    with pytest.raises(AdapterError) as error:
        run(
            AdapterRegistry((TestAdapter(descriptor(), mode=mode),)), (source("A.txt"),)
        )
    assert error.value.adapter_key == "test" and error.value.stage == "analyze"
    assert error.value.__cause__ is not None


def test_recovered_errors_downgrade_coverage_and_preserve_ranges() -> None:
    _, results = run(
        AdapterRegistry((TestAdapter(descriptor(), mode="error"),)), (source("A.txt"),)
    )
    report = next(e for e in results[0].entities if isinstance(e, SourceAnalysis))
    assert report.capabilities[0].status == "PARTIAL"
    assert report.diagnostics[0].code == "parse.error"
    assert report.diagnostics[0].source_range.start.line == 1


def test_explicit_unsupported_capability_is_not_lost() -> None:
    _, results = run(
        AdapterRegistry((TestAdapter(descriptor(), mode="unsupported"),)),
        (source("A.txt"),),
    )
    assert results[0].entities[0].capabilities[0].status == "UNSUPPORTED"


@pytest.mark.parametrize("profile", JAVA_PROFILES)
def test_each_java_profile_conforms_to_registry_contract(profile: str) -> None:
    _, results = run(
        AdapterRegistry((JavaSourceAdapter(profile=profile),)),
        (source("A.java", 'class A{void m(){String q="select id from t";}}', "java"),),
    )
    report = next(e for e in results[0].entities if isinstance(e, SourceAnalysis))
    assert report.adapter_key == "java." + profile
    assert any(cap.capability == "java.symbols" for cap in report.capabilities)


def test_java_symbols_recovery_and_semantic_failure_have_structured_diagnostics() -> (
    None
):
    src = source("A.java", "class A { void m( {", "java")
    _, results = run(AdapterRegistry((JavaSourceAdapter(profile="symbols"),)), (src,))
    report = next(e for e in results[0].entities if isinstance(e, SourceAnalysis))
    assert report.diagnostics and all(
        c.status != "COMPLETE" for c in report.capabilities
    )
    with pytest.raises(AdapterError) as error:
        run(AdapterRegistry((JavaSourceAdapter(profile="orm"),)), (src,))
    assert error.value.stage == "prepare" and error.value.issues[0].path == "A.java"
    assert error.value.issues[0].diagnostic.source_range is not None


def test_invalid_utf8_is_reported_with_captured_byte_coordinates() -> None:
    good = source("A.java", "x", "java")
    content = b"\xff"
    src = SourceInput(
        good.file.model_copy(
            update={"content_sha256": hashlib.sha256(content).hexdigest()}
        ),
        content,
    )
    _, results = run(AdapterRegistry((JavaSourceAdapter(profile="symbols"),)), (src,))
    report = next(e for e in results[0].entities if isinstance(e, SourceAnalysis))
    assert report.diagnostics[0].code == "java.INVALID_UTF8"


def test_java_catalog_is_descriptive_not_implicit_multi_registration() -> None:
    assert len(java_adapter_catalog()) == len(JAVA_PROFILES)
    with pytest.raises(ValueError, match="suffix"):
        AdapterRegistry(
            (JavaSourceAdapter(profile="calls"), JavaSourceAdapter(profile="orm"))
        )


def test_multiple_adapters_dispatch_only_their_requested_subsets() -> None:
    registry = AdapterRegistry(
        (
            TestAdapter(descriptor("one", ".txt")),
            TestAdapter(descriptor("two", ".spec")),
        )
    )
    _, results = run(registry, (source("A.txt"), source("B.spec")))
    assert {
        next(e for e in result.entities if isinstance(e, SourceAnalysis)).adapter_key
        for result in results
    } == {"one", "two"}


def test_snapshot_metadata_cannot_claim_complete_capability_with_error() -> None:
    _, results = run(
        AdapterRegistry((TestAdapter(descriptor(), mode="error"),)), (source("A.txt"),)
    )
    report = next(e for e in results[0].entities if isinstance(e, SourceAnalysis))
    bad = {
        **report.model_dump(),
        "capabilities": (
            Coverage(
                capability="test.symbols", analyzer_version="1", status="COMPLETE"
            ),
        ),
    }
    with pytest.raises(ValidationError, match="complete"):
        SourceAnalysis(**bad)


def test_sql_candidate_parse_errors_are_structured_without_losing_safe_facts() -> None:
    _, results = run(
        AdapterRegistry((JavaSourceAdapter(profile="semantic"),)),
        (source("A.java", 'class A{void m(){String q="select * from ";}}', "java"),),
    )
    report = next(e for e in results[0].entities if isinstance(e, SourceAnalysis))
    assert any(d.code == "sql.CANDIDATE_PARSE_ERROR" for d in report.diagnostics)
    assert all(c.status != "COMPLETE" for c in report.capabilities)
