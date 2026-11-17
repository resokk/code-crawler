import asyncio
import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_java_execution import analyze as executions
from test_sql_construction import analyze as constructions
from tree_sitter import Parser

from code_crawler import java


def uncached(node):
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def root(content):
    return Parser(java._LANGUAGE).parse(content).root_node


def test_node_keys_empty_none_and_repeated_wrapper():
    node = root(b"class A {}")
    with java._text_scope() as cache:
        assert java._text(None) == ""
        assert java._text(node) == "class A {}"
        assert java._text(node) == "class A {}"
        assert cache.misses == 1 and cache.hits == 1
        # Tree-sitter may return another Python wrapper for the same C node.
        child = node.named_children[0]
        assert java._text(child) == java._text(node.named_children[0])
        empty = root(b"")
        assert java._text(empty) == java._text(empty) == ""
        assert cache.hits == 3
    assert not cache.texts and cache.bytes == 0
    assert java._TEXT_STATE.cache is None


def test_successive_trees_and_error_release_entries():
    caches = []

    @java._cached_text
    def read(content, fail=False):
        cache = java._TEXT_STATE.cache
        assert not cache.texts
        caches.append(cache)
        value = java._text(root(content))
        if fail:
            raise ValueError("failure")
        return value

    assert read(b"class A {}") == "class A {}"
    with pytest.raises(ValueError, match="failure"):
        read(b"class Broken {}", True)
    assert read(b"class B {}") == "class B {}"
    assert len({id(cache) for cache in caches}) == 3
    assert all(not cache.texts and cache.bytes == 0 for cache in caches)
    assert java._TEXT_STATE.cache is None


def test_retained_nodes_from_distinct_trees_cannot_return_stale_text():
    with java._text_scope() as cache:
        for i in range(100):
            node = root(f"class Class{i} {{}}".encode())
            assert java._text(node) == f"class Class{i} {{}}"
        assert len(cache.texts) == 100
    assert not cache.texts


def test_caps_and_replacement_decoding_preserve_text(monkeypatch):
    monkeypatch.setattr(java, "_TEXT_MAX_ENTRIES", 1)
    monkeypatch.setattr(java, "_TEXT_MAX_BYTES", 128)
    first, second = root(b"A"), root(b"B")
    with java._text_scope() as cache:
        assert java._text(first) == "A"
        assert java._text(second) == java._text(second) == "B"
        assert len(cache.texts) == 1 and cache.misses == 3
        assert java._text(root(b"\xff")) == "\ufffd"
        assert java._text(root(b"a" * 1000)) == "a" * 1000
        assert cache.bytes <= 128
    monkeypatch.setattr(java, "_TEXT_MAX_BYTES", 0)
    with java._text_scope() as cache:
        assert java._text(first) == java._text(first) == "A"
        assert not cache.texts and cache.misses == 2


def test_nested_helpers_reuse_scope_and_parallel_workers_are_isolated():
    barrier = threading.Barrier(2)

    @java._cached_text
    def inner(node):
        return java._text(node), java._TEXT_STATE.cache

    @java._cached_text
    def work(content):
        cache = java._TEXT_STATE.cache
        node = root(content)
        barrier.wait(timeout=5)
        value, nested = inner(node)
        assert nested is cache
        barrier.wait(timeout=5)
        assert java._text(node) == value
        return value, cache

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(work, b"class One {}")
        two = pool.submit(work, b"class Two {}")
        first, second = one.result(), two.result()
        assert first[0] == "class One {}" and second[0] == "class Two {}"
        assert first[1] is not second[1]
        assert not first[1].texts and not second[1].texts

    async def reused_worker():
        @java._cached_text
        def single(content):
            value = java._text(root(content))
            return value, java._TEXT_STATE.cache

        results = await asyncio.gather(
            *(asyncio.to_thread(single, f"class C{i} {{}}".encode()) for i in range(64))
        )
        assert len({id(cache) for _, cache in results}) == 64
        assert all(not cache.texts for _, cache in results)

    asyncio.run(reused_worker())


@pytest.mark.parametrize(
    "source",
    [
        'class A { void m(){use("select id from t");} }',
        'class A { static final String Q="select id from t"; void m(boolean f,String p){String q=Q;if(f){q+=p;}use(q);} }',
        'class A { void m(boolean f){StringBuilder q=new StringBuilder("select id from t");if(f){q.append(" where id=1");}else{q.reverse();}use(q.toString());} }',
        'import java.sql.*;class A {void m(Connection c,boolean f) throws Exception {String q="select id from t";if(f){q+=" where id=1";}c.prepareStatement(q).execute();}}',
        'class A { void m(){String q="select id from t";'
        + 'if(flag){q+=" x";}else{q+=" y";}' * 10
        + "use(q);}}",
    ],
)
def test_complete_facts_match_direct_decoding(monkeypatch, source):
    cached = [run(source).model_dump_json() for run in (constructions, executions)]
    monkeypatch.setattr(java, "_text", uncached)
    assert cached == [
        run(source).model_dump_json() for run in (constructions, executions)
    ]


@pytest.mark.parametrize(
    "source",
    [
        b"class A {}",
        b"class A { void broken( }",
        b"\xff",
        "class Caf\u00e9 { void m(){use(\"select '\u0416' from t\");}}".encode(),
    ],
)
def test_parse_diagnostics_and_legacy_queries_match(monkeypatch, source):
    cached = java.analyze(source)
    symbols = copy.deepcopy(cached.symbols)
    monkeypatch.setattr(java, "_text", uncached)
    direct = java.analyze(source)
    assert symbols == direct.symbols
    assert cached.diagnostics == direct.diagnostics
    assert cached.coverage == direct.coverage
    assert cached._constant_scopes == direct._constant_scopes


def test_entire_worker_slice_uses_fresh_file_scopes(monkeypatch):
    from contextlib import contextmanager

    from test_java_calls import source

    from code_crawler.java_sql import JavaSqlAnalyzer

    sources = tuple(
        source(
            f"C{i}.java", f'class C{i} {{ void m(){{use("select id from t{i}");}} }}'
        )
        for i in range(64)
    )
    analyzer = JavaSqlAnalyzer(sources)
    scopes = []
    original = java._text_scope

    @contextmanager
    def traced():
        with original() as cache:
            scopes.append(cache)
            yield cache

    monkeypatch.setattr(java, "_text_scope", traced)
    assert len(asyncio.run(analyzer(sources))) == 64
    assert len(scopes) == len({id(cache) for cache in scopes}) == 64
    assert all(not cache.texts and cache.bytes == 0 for cache in scopes)


def test_orm_profile_and_cross_file_catalog_facts_match(monkeypatch):
    from test_java_orm import analyze as orm

    sources = (
        'import jakarta.persistence.*; @Entity @Table(name="users") class User { @Id long id; String name; }',
        'import java.sql.*; class Repo { void run(Connection c,int id) throws Exception {PreparedStatement p=c.prepareStatement("select name from users where id=?");p.setInt(1,id);p.executeQuery();}}',
    )
    cached = orm(*sources).model_dump_json()
    monkeypatch.setattr(java, "_text", uncached)
    assert orm(*sources).model_dump_json() == cached


def test_cancelled_to_thread_cleans_in_worker_after_it_finishes():
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    observed = []

    @java._cached_text
    def operation():
        java._text(root(b"class Cancelled {}"))
        observed.append(java._TEXT_STATE.cache)
        started.set()
        assert release.wait(timeout=5)

    def worker():
        try:
            operation()
        finally:
            observed.append(getattr(java._TEXT_STATE, "cache", None))
            finished.set()

    async def run():
        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
        assert await asyncio.to_thread(finished.wait, 5)

    asyncio.run(run())
    assert not observed[0].texts and observed[1] is None
