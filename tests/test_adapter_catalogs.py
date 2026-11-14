import asyncio
from dataclasses import dataclass

import pytest
from test_source_adapters import descriptor, source

from code_crawler.incremental import FileAnalysis
from code_crawler.source_adapters import (
    AdapterCatalog,
    AdapterError,
    AdapterFileResult,
    AdapterRegistry,
)
from code_crawler.ucm import Position, SourceRange


@dataclass
class FixtureAdapter:
    key: str
    suffix: str
    catalogs: object = ()
    consumer: bool = False
    drift: bool = False

    @property
    def descriptor(self):
        return descriptor(self.key, self.suffix)

    async def prepare(self, sources):
        adapter = self

        class Prepared:
            analysis_version = "fixture/1"

            async def export_catalogs(self):
                if adapter.drift:
                    self.analysis_version = "changed"
                return adapter.catalogs

            async def __call__(self, selected):
                return tuple(
                    AdapterFileResult(analysis=FileAnalysis(path=s.file.path))
                    for s in selected
                )

        class Consumer(Prepared):
            catalog_keys = ("local.symbols",)

            async def with_catalogs(self, catalogs):
                with pytest.raises(TypeError):
                    catalogs["mutated"] = AdapterCatalog(key="no", version="1")
                self.analysis_version = "bound:" + ",".join(sorted(catalogs))
                return self

        return Consumer() if adapter.consumer else Prepared()


class RangedCatalog(AdapterCatalog):
    location: SourceRange


class MutableCatalog(AdapterCatalog):
    values: list[str]


def prepare(adapters, sources=()):
    return asyncio.run(AdapterRegistry(adapters).prepare(sources))


def test_catalog_binding_is_order_independent_and_read_only() -> None:
    catalog = AdapterCatalog(key="local.symbols", version="1")
    provider = FixtureAdapter("provider", ".p", (catalog,))
    consumer = FixtureAdapter("consumer", ".c", consumer=True)
    first = prepare((provider, consumer))
    reverse = prepare((consumer, provider))
    assert first.analysis_version == reverse.analysis_version
    assert first.prepared["consumer"][1].analysis_version == "bound:local.symbols"


@pytest.mark.parametrize(
    "catalogs",
    [[], ("untyped",), (MutableCatalog(key="local", version="1", values=["mutable"]),)],
)
def test_catalog_exports_must_be_typed_and_deeply_immutable(catalogs) -> None:
    with pytest.raises(AdapterError) as error:
        prepare(
            (
                FixtureAdapter("provider", ".p", catalogs),
                FixtureAdapter("consumer", ".c", consumer=True),
            )
        )
    assert error.value.stage == "catalog"


def test_duplicate_catalog_keys_never_depend_on_adapter_order() -> None:
    catalog = AdapterCatalog(key="same", version="1")
    with pytest.raises(AdapterError, match="duplicate"):
        prepare(
            (
                FixtureAdapter("one", ".one", (catalog,)),
                FixtureAdapter("two", ".two", (catalog,)),
                FixtureAdapter("consumer", ".c", consumer=True),
            )
        )


@pytest.mark.parametrize("mode", ["foreign", "mismatch", "other-adapter", "bad-range"])
def test_catalog_provenance_and_source_ranges_are_validated(mode: str) -> None:
    own = source("a.p", "text")
    other = source("b.c", "text")
    file = own.file
    if mode == "foreign":
        file = source("foreign.p").file
    elif mode == "mismatch":
        file = source("a.p", "different captured bytes").file
    elif mode == "other-adapter":
        file = other.file
    catalog = AdapterCatalog(key="local", version="1", source_files=(file,))
    if mode == "bad-range":
        catalog = RangedCatalog(
            key="local",
            version="1",
            source_files=(file,),
            location=SourceRange(
                source_file_id=file.id,
                start=Position(line=999, byte_column=0),
                end=Position(line=999, byte_column=1),
            ),
        )
    with pytest.raises(AdapterError):
        prepare(
            (
                FixtureAdapter("provider", ".p", (catalog,)),
                FixtureAdapter("consumer", ".c", consumer=True),
            ),
            (own, other),
        )


def test_catalog_export_cannot_change_provider_version() -> None:
    with pytest.raises(AdapterError, match="version"):
        prepare(
            (
                FixtureAdapter("provider", ".p", drift=True),
                FixtureAdapter("consumer", ".c", consumer=True),
            )
        )
