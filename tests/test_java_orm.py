import asyncio
import hashlib
from uuid import UUID

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_orm import JavaOrmAnalyzer
from code_crawler.ucm import (
    DataAccess,
    EntityType,
    OrmMapping,
    OrmOperation,
    OrmQuery,
    Relation,
    RelationKind,
    SourceFile,
    SqlExecute,
    SqlStatement,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def analyze(*texts: str) -> UcmBatch:
    sources = []
    for index, text in enumerate(texts):
        name = f"A{index}.java"
        content = text.encode()
        file = SourceFile(
            repository_id=str(REPO),
            logical_key=name,
            id=logical_id(str(REPO), EntityType.SOURCE_FILE, name),
            name=name,
            path=name,
            language="java",
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        sources.append(SourceInput(file, content))
    sources = tuple(sources)
    results = asyncio.run(JavaOrmAnalyzer(sources)(sources))
    batch = UcmBatch(
        repository_id=REPO,
        entities=tuple(s.file for s in sources)
        + tuple(e for r in results for e in r.entities),
    )
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    return batch


def mappings(batch: UcmBatch) -> list[OrmMapping]:
    return [e for e in batch.entities if isinstance(e, OrmMapping)]


def operations(batch: UcmBatch) -> list[OrmOperation]:
    return [e for e in batch.entities if isinstance(e, OrmOperation)]


def relations(batch: UcmBatch, kind: RelationKind) -> list[Relation]:
    return [
        e for e in batch.entities if isinstance(e, Relation) and e.relation_kind == kind
    ]


ENTITY = '@Entity @Table(name="users") class User {@Id @Column(name="user_id") int id; @Column(name="user_name",nullable=false) String name; @Transient String ignored; static String constant; transient String cache;}'


def test_field_mappings_names_flags_and_transient_exclusion() -> None:
    batch = analyze("import jakarta.persistence.*;" + ENTITY)
    assert {
        m.attribute_name for m in mappings(batch) if m.mapping_kind == "ATTRIBUTE"
    } == {"id", "name"}
    entity = next(m for m in mappings(batch) if m.mapping_kind == "ENTITY")
    assert entity.table_name.text == "users" and entity.access_mode == "FIELD"
    name = next(m for m in mappings(batch) if m.attribute_name == "name")
    assert name.column_name.text == "user_name" and name.nullable is False


def test_property_access_and_javabeans_acronym() -> None:
    batch = analyze(
        'import javax.persistence.*;@Entity class User {int id;String URL;@Id public int getId(){return id;} @Column(name="url") public String getURL(){return URL;}public void setURL(String x){URL=x;}}'
    )
    assert {
        m.attribute_name for m in mappings(batch) if m.mapping_kind == "ATTRIBUTE"
    } == {"id", "URL"}
    assert all(m.access_mode == "PROPERTY" for m in mappings(batch))


def test_custom_annotation_and_method_names_are_not_jpa() -> None:
    batch = analyze(
        "@interface Entity{} @Entity class User{int id;} class EntityManager {void persist(User u){}} class A {void m(EntityManager em,User u){em.persist(u);}}"
    )
    assert not mappings(batch) and not operations(batch)


def test_persist_merge_remove_find_and_reference_intents() -> None:
    batch = analyze(
        "import jakarta.persistence.*;"
        + ENTITY
        + "class A {void m(EntityManager em,User u,int id){em.persist(u);em.merge(u);em.remove(u);em.find(User.class,id);em.getReference(User.class,id);em.refresh(u);em.flush();}}"
    )
    assert {o.operation_kind for o in operations(batch)} == {
        "PERSIST",
        "MERGE",
        "REMOVE",
        "FIND",
        "GET_REFERENCE",
        "REFRESH",
        "FLUSH",
    }
    assert (
        next(
            o for o in operations(batch) if o.operation_kind == "GET_REFERENCE"
        ).effect_kind
        == "REFERENCE"
    )
    assert (
        next(o for o in operations(batch) if o.operation_kind == "MERGE").effect_kind
        == "MERGE"
    )
    assert not any(isinstance(e, SqlExecute) for e in batch.entities)
    targets = relations(batch, RelationKind.ORM_TARGET_ENTITY)
    assert sum(r.resolution.status == "RESOLVED" for r in targets) == 6


def test_jpql_entity_and_property_names_are_not_sql_tables() -> None:
    batch = analyze(
        "import jakarta.persistence.*;"
        + ENTITY
        + 'class A {void m(EntityManager em){em.createQuery("select u.name from User u where u.id=:id",String.class).getResultList();}}'
    )
    assert [o.operation_kind for o in operations(batch)] == ["QUERY_READ"]
    assert (
        relations(batch, RelationKind.ORM_QUERY_ENTITY)[0].resolution.status
        == "RESOLVED"
    )
    assert relations(batch, RelationKind.ORM_QUERY_READS_ATTRIBUTE)
    assert not any(isinstance(e, SqlExecute) for e in batch.entities)


def test_jpql_bulk_update_writes_mapped_property() -> None:
    batch = analyze(
        "import jakarta.persistence.*;"
        + ENTITY
        + 'class A {void m(EntityManager em){em.createQuery("update User u set u.name=:name where u.id=:id").executeUpdate();}}'
    )
    assert operations(batch)[0].effect_kind == "WRITE"
    assert (
        relations(batch, RelationKind.ORM_QUERY_WRITES_ATTRIBUTE)[0].resolution.status
        == "RESOLVED"
    )
    assert not any(isinstance(e, SqlExecute) for e in batch.entities)


def test_query_creation_and_annotation_declaration_do_not_execute() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@NamedQuery(name="all",query="select u from User u")'
        + ENTITY
        + 'class A {void m(EntityManager em){Query q=em.createQuery("select u from User u");}}'
    )
    assert any(isinstance(e, OrmQuery) for e in batch.entities)
    assert not operations(batch) and not any(
        isinstance(e, SqlExecute) for e in batch.entities
    )


def test_native_query_terminal_reuses_sql_semantics() -> None:
    batch = analyze(
        'import jakarta.persistence.*;class A {void m(EntityManager em){em.createNativeQuery("select id from users").getResultList();}}'
    )
    assert len([e for e in batch.entities if isinstance(e, SqlExecute)]) == 1
    assert any(
        isinstance(e, SqlStatement) and e.parse_status == "COMPLETE"
        for e in batch.entities
    )
    assert any(
        isinstance(e, DataAccess) and e.table_name and e.table_name.text == "users"
        for e in batch.entities
    )


def test_native_select_constant_outside_discovery_heuristic() -> None:
    batch = analyze(
        'import jakarta.persistence.*;class A {void m(EntityManager em){em.createNativeQuery("select 1").getSingleResult();}}'
    )
    assert any(
        isinstance(e, SqlStatement) and e.text == "select 1" for e in batch.entities
    )
    assert any(isinstance(e, SqlExecute) for e in batch.entities)


def test_named_query_declaration_reference_and_execution_across_files() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@NamedQuery(name="User.all",query="select u from User u")'
        + ENTITY,
        'import jakarta.persistence.*;class A {void m(EntityManager em){em.createNamedQuery("User.all").getResultList();}}',
    )
    assert (
        relations(batch, RelationKind.ORM_NAMED_QUERY)[0].resolution.status
        == "RESOLVED"
    )
    assert operations(batch) and not any(
        isinstance(e, SqlExecute) for e in batch.entities
    )


def test_named_native_query_is_native_execution_not_jpql() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@NamedNativeQuery(name="native.all",query="select id from users")'
        + ENTITY,
        'import jakarta.persistence.*;class A {void m(EntityManager em){em.createNamedQuery("native.all").getResultList();}}',
    )
    assert (
        relations(batch, RelationKind.ORM_NAMED_QUERY)[0].resolution.status
        == "RESOLVED"
    )
    assert any(isinstance(e, SqlExecute) for e in batch.entities)


def test_query_aliases_and_fluent_parameters_preserve_origin() -> None:
    batch = analyze(
        "import jakarta.persistence.*;"
        + ENTITY
        + 'class A {void m(EntityManager em,int id){Query q=em.createQuery("select u from User u");Query a=q;a.setParameter("id",id).getResultList();}}'
    )
    assert (
        relations(batch, RelationKind.ORM_EXECUTES_QUERY)[0].resolution.status
        == "RESOLVED"
    )


def test_unknown_query_origin_and_escape_remain_unknown() -> None:
    batch = analyze(
        'import jakarta.persistence.*;class A {void m(EntityManager em,Query external){Query q=em.createNativeQuery("select id from users");unknown(q);q.getResultList();external.executeUpdate();}}'
    )
    assert operations(batch)
    assert all(
        r.resolution.status == "UNRESOLVED"
        for r in relations(batch, RelationKind.ORM_EXECUTES_QUERY)
    )
    assert not any(isinstance(e, SqlExecute) for e in batch.entities)


def test_inheritance_and_relationships_are_explicitly_partial() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@Entity class User extends Base {@Id int id;@ManyToOne @JoinColumn(name="owner_id") User owner;}class Base{}'
    )
    assert (
        next(m for m in mappings(batch) if m.mapping_kind == "ENTITY").status
        == "PARTIAL"
    )
    assert (
        next(m for m in mappings(batch) if m.attribute_name == "owner").status
        == "PARTIAL"
    )


def test_criteria_api_is_not_invented_jpql_text() -> None:
    batch = analyze(
        "import jakarta.persistence.*;class A {void m(EntityManager em,Object criteria){em.createQuery(criteria).getResultList();}}"
    )
    assert any(
        isinstance(e, OrmQuery)
        and e.query_kind == "CRITERIA"
        and e.status == "UNSUPPORTED"
        for e in batch.entities
    )
    assert not any(isinstance(e, SqlExecute) for e in batch.entities)


def test_spring_query_annotations_distinguish_native_flag() -> None:
    batch = analyze(
        'import org.springframework.data.jpa.repository.Query;interface Repo {@Query("select u from User u") Object all();@Query(value="select id from users",nativeQuery=true) Object nativeAll();}'
    )
    assert {e.query_kind for e in batch.entities if isinstance(e, OrmQuery)} == {
        "JPQL",
        "NATIVE",
    }
    assert not operations(batch)


def test_duplicate_named_query_definitions_are_ambiguous() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@NamedQuery(name="all",query="select u from User u")'
        + ENTITY,
        'import jakarta.persistence.*;@Entity @NamedQuery(name="all",query="select x from Other x") class Other {@Id int id;}class A{void m(EntityManager em){em.createNamedQuery("all").getResultList();}}',
    )
    assert (
        relations(batch, RelationKind.ORM_NAMED_QUERY)[0].resolution.status
        == "AMBIGUOUS"
    )


def test_mixed_native_and_jpql_query_branches_are_not_definite_sql() -> None:
    batch = analyze(
        "import jakarta.persistence.*;"
        + ENTITY
        + 'class A {void m(EntityManager em,boolean flag){Query q;if(flag){q=em.createNativeQuery("select id from users");}else{q=em.createQuery("select u from User u");}q.getResultList();}}'
    )
    assert (
        relations(batch, RelationKind.ORM_EXECUTES_QUERY)[0].resolution.status
        == "PARTIAL"
    )
    assert relations(batch, RelationKind.EXECUTES_SQL)[0].resolution.status == "PARTIAL"


def test_named_native_select_constant_creates_cross_file_sql_facts() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@NamedNativeQuery(name="one",query="select 1")'
        + ENTITY,
        'import jakarta.persistence.*;class A {void m(EntityManager em){em.createNamedQuery("one").getSingleResult();}}',
    )
    assert any(
        isinstance(e, SqlStatement) and e.text == "select 1" for e in batch.entities
    )
    assert any(isinstance(e, SqlExecute) for e in batch.entities)


def test_unknown_native_sql_retains_execution_without_fabricated_accesses() -> None:
    batch = analyze(
        "import jakarta.persistence.*;class A {void m(EntityManager em,String sql){em.createNativeQuery(sql).executeUpdate();}}"
    )
    assert any(isinstance(e, SqlExecute) for e in batch.entities)
    assert not any(isinstance(e, DataAccess) for e in batch.entities)
    assert (
        relations(batch, RelationKind.USES_SQL_CONSTRUCTION)[0].resolution.status
        == "UNRESOLVED"
    )


def test_unknown_property_has_explicit_unresolved_reference() -> None:
    batch = analyze(
        "import jakarta.persistence.*;"
        + ENTITY
        + 'class A{void m(EntityManager em){em.createQuery("select u.missing from User u").getResultList();}}'
    )
    assert (
        relations(batch, RelationKind.ORM_QUERY_READS_ATTRIBUTE)[0].resolution.status
        == "UNRESOLVED"
    )


def test_unknown_access_and_embedded_mapping_are_partial() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@Entity class User {@Column(name="id") int id;@Embedded Object details;}'
    )
    assert (
        next(m for m in mappings(batch) if m.mapping_kind == "ENTITY").status
        == "PARTIAL"
    )


def test_fully_qualified_annotations_and_quoted_identifier_spelling() -> None:
    batch = analyze(
        '@jakarta.persistence.Entity @jakarta.persistence.Table(name="\\"Users\\"") class User {@jakarta.persistence.Id @jakarta.persistence.Column(name="\\"ID\\"") int id;}'
    )
    entity = next(m for m in mappings(batch) if m.mapping_kind == "ENTITY")
    assert entity.table_name.quoted and entity.table_name.text == "Users"


def test_jakarta_namespace_is_kept_for_var_query_handles() -> None:
    batch = analyze(
        'import jakarta.persistence.*;class A{void m(EntityManager em){var q=em.createNativeQuery("select 1");q.getSingleResult();}}'
    )
    assert operations(batch)[0].api.startswith("jakarta.persistence.")


def test_unknown_spring_native_flag_does_not_guess_jpql_domain() -> None:
    batch = analyze(
        'import org.springframework.data.jpa.repository.Query;interface Repo{@Query(value="select id from users",nativeQuery=FLAG) Object all();}'
    )
    assert any(
        isinstance(e, OrmQuery) and e.query_kind == "UNKNOWN" and e.status == "PARTIAL"
        for e in batch.entities
    )
    assert not operations(batch)


def test_unsupported_hql_with_clause_is_not_physical_sql_execution() -> None:
    batch = analyze(
        "import jakarta.persistence.*;"
        + ENTITY
        + 'class A{void m(EntityManager em){em.createQuery("with x as (select u from User u) select x from x").getResultList();}}'
    )
    assert any(
        isinstance(e, OrmQuery) and e.status == "UNSUPPORTED" for e in batch.entities
    )
    assert not any(isinstance(e, SqlExecute) for e in batch.entities)


def test_native_creation_without_terminal_is_not_execution() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@NamedNativeQuery(name="all",query="select id from users")'
        + ENTITY
        + 'class A{void m(EntityManager em){Query q=em.createNativeQuery("select id from users");}}'
    )
    assert any(isinstance(e, SqlStatement) for e in batch.entities)
    assert not operations(batch) and not any(
        isinstance(e, SqlExecute) for e in batch.entities
    )


def test_operation_effect_tampering_is_rejected() -> None:
    import pytest
    from pydantic import ValidationError

    batch = analyze(
        "import jakarta.persistence.*;"
        + ENTITY
        + "class A{void m(EntityManager em,User u){em.merge(u);}}"
    )
    operation = operations(batch)[0]
    bad = operation.model_copy(update={"effect_kind": "INSERT"})
    with pytest.raises(ValidationError, match="effect must match"):
        UcmBatch(
            repository_id=REPO,
            entities=tuple(bad if e.id == bad.id else e for e in batch.entities),
        )


def test_custom_entity_name_is_not_replaced_by_simple_class_name() -> None:
    batch = analyze(
        'import jakarta.persistence.*;@Entity(name="Person") class User{@Id int id;}class A{void m(EntityManager em){em.createQuery("select p from Person p").getResultList();em.createQuery("select u from User u").getResultList();}}'
    )
    assert {
        r.resolution.status for r in relations(batch, RelationKind.ORM_QUERY_ENTITY)
    } == {"RESOLVED", "UNRESOLVED"}
