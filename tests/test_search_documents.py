import hashlib
import json

from test_source_adapters import run, source

from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.search_documents import project
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import (
    DatabaseObject,
    EntityType,
    database_object_key,
    logical_id,
)

REPO = """package app;
import java.sql.Connection;
import java.sql.PreparedStatement;
public class Repo {
    private final Connection connection;
    public Repo(Connection connection) { this.connection = connection; }
    public void load(String id) throws Exception {
        PreparedStatement ps = connection.prepareStatement("SELECT name FROM users WHERE id = ?");
        ps.executeQuery();
    }
}
"""
SERVICE = """package app;
public class Service {
    private final Repo repo;
    public Service(Repo repo) { this.repo = repo; }
    public void handle(String id) throws Exception { repo.load(id); }
}
"""
GROOVY = "class Job {\n  def run() { 1 }\n}\n"


def entities() -> tuple:
    sources = (
        source("Repo.java", REPO, "java"),
        source("Service.java", SERVICE, "java"),
        source("Job.groovy", GROOVY, "groovy"),
    )
    registry = AdapterRegistry(
        (JavaSourceAdapter(profile="orm"), GroovySourceAdapter())
    )
    _, results = run(registry, sources)
    return tuple(s.file for s in sources) + tuple(
        entity for result in results for entity in result.entities
    )


def test_documents_state_only_recorded_facts() -> None:
    documents = {(d.kind, d.title): d for d in project(entities())}

    load = documents["SYMBOL", "app.Repo.load(String)"]
    assert load.text.splitlines()[0] == "METHOD app.Repo.load(String)"
    assert "language: java" in load.text and "file: Repo.java:7-10" in load.text
    assert load.path == "Repo.java" and load.language == "java"
    assert not any(kind == "SYMBOL" and "id" == title for kind, title in documents)

    job = next(d for d in documents.values() if d.language == "groovy")
    assert job.kind == "SYMBOL" and job.path == "Job.groovy"

    statement = next(d for d in documents.values() if d.kind == "SQL_STATEMENT")
    lines = statement.text.splitlines()
    assert lines[0] == "SELECT statement, dialect postgres, parse COMPLETE"
    assert lines[1] == "SELECT name FROM users WHERE id = ?"
    assert "reads table users as source" in lines
    assert "reads column users.name as select" in lines
    assert (
        "executed by app.Repo.load(String) via "
        "java.sql.PreparedStatement.executeQuery [INFERRED]" in lines
    )

    handle = documents["CALL_SUMMARY", "Calls of app.Service.handle(String)"]
    assert "calls: app.Repo.load(String) [INFERRED]" in handle.text
    assert "coverage: java.calls PARTIAL" in handle.text
    summary = documents["CALL_SUMMARY", "Calls of app.Repo.load(String)"]
    assert "called by: app.Service.handle(String) [INFERRED]" in summary.text
    # JDBC targets are outside the repository: counted with the reason, never named.
    assert any(
        line.split(" ", 1)[1].startswith("UNRESOLVED calls: ")
        for line in summary.text.splitlines()
    )
    assert "java.sql" not in summary.text


def test_documents_are_deterministic_and_content_addressed() -> None:
    facts = entities()
    first = list(project(facts))
    assert first == list(project(tuple(reversed(facts))))
    assert len({d.id for d in first}) == len(first)
    for document in first:
        assert (
            document.content_sha256
            == hashlib.sha256(f"{document.title}\n{document.text}".encode()).hexdigest()
        )


def test_database_object_document() -> None:
    key = database_object_key("main", "v1", "TABLE", "app", "public", "users")
    file_id = logical_id("repo", EntityType.SOURCE_FILE, "schema")
    logical_key = json.dumps(["database.object", file_id, key], separators=(",", ":"))
    table = DatabaseObject(
        repository_id="repo",
        logical_key=logical_key,
        id=logical_id("repo", EntityType.DATABASE_OBJECT, logical_key),
        name="users",
        projection_file_id=file_id,
        database_key="main",
        version_key="v1",
        schema_fingerprint="b" * 64,
        object_key=key,
        object_kind="TABLE",
        catalog_name="app",
        schema_name="public",
        table_name="users",
    )
    (document,) = project((table,))
    assert (document.kind, document.title) == ("DATABASE_OBJECT", "app.public.users")
    assert document.text == "TABLE app.public.users\ndatabase: main version v1"
