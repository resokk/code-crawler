import json

import pytest
from test_search_documents import entities
from test_source_adapters import REPO

from code_crawler.ingestion import UcmBatch
from code_crawler.search_storage import _records
from code_crawler.ucm import EntityType, OrmMapping, OrmQuery, Symbol, logical_id


def test_redacted_content_and_deterministic_projection() -> None:
    facts = entities()
    owner = next(e for e in facts if isinstance(e, Symbol))
    query = OrmQuery(
        repository_id=str(REPO),
        logical_key="orm-query",
        name="query",
        id=logical_id(str(REPO), EntityType.ORM_QUERY, "orm-query"),
        owner_symbol_id=owner.id,
        query_kind="JPQL",
        text="SELECT x FROM Account x WHERE x.password = 'secret'",
        status="PARTIAL",
        reasons=("missing context",),
    )
    mapping = OrmMapping(
        repository_id=str(REPO),
        logical_key="orm-map",
        name="Account",
        id=logical_id(str(REPO), EntityType.ORM_MAPPING, "orm-map"),
        symbol_id=owner.id,
        owner_symbol_id=owner.id,
        entity_name="Account",
        mapping_kind="ENTITY",
        entity_role="ENTITY",
        access_mode="UNKNOWN",
        status="PARTIAL",
        reasons=("missing table",),
    )
    # Projection consumes facts; cross-reference validation belongs to ingestion.
    batch = UcmBatch.model_construct(
        repository_id=REPO, entities=(*facts, query, mapping)
    )

    def redact(text: str) -> str:
        return text.replace("secret", "[REDACTED]").replace(
            "SELECT name", "SELECT [REDACTED]"
        )

    first = _records(batch, redact)
    assert first == _records(
        UcmBatch.model_construct(
            repository_id=REPO, entities=tuple(reversed(batch.entities))
        ),
        redact,
    )
    assert len(first) == len({row[0] for row in first})
    documents = {row[2]: json.loads(row[3]) for row in first}
    assert "SELECT" not in documents["SQL_STATEMENT"]["summary"].splitlines()[1]
    assert documents["SQL_STATEMENT"]["redacted_source"].startswith("SELECT [REDACTED]")
    assert documents["ORM_QUERY"]["redacted_source"].endswith("'[REDACTED]'")
    assert "password" not in documents["ORM_QUERY"]["summary"]
    assert "status PARTIAL" in documents["ORM_MAPPING"]["summary"]
    assert "secret" not in json.dumps(first)
    changed = _records(batch, lambda text: text)
    assert [r[0] for r in first] == [r[0] for r in changed]
    assert [r[4] for r in first] != [r[4] for r in changed]
    with pytest.raises(RuntimeError, match="policy failure"):

        def fail(text: str) -> str:
            raise RuntimeError("policy failure")

        _records(batch, fail)


@pytest.mark.parametrize("status", ["AMBIGUOUS", "UNRESOLVED"])
def test_uncertainty_is_not_promoted(status: str) -> None:
    from code_crawler.ucm import EntityRef, Relation, Resolution

    facts = entities()
    symbols = [e for e in facts if isinstance(e, Symbol)]
    relation = next(e for e in facts if isinstance(e, Relation))
    resolution = Resolution(
        status=status,
        reason="missing context",
        candidates=tuple(
            EntityRef(id=e.id, entity_type=e.entity_type) for e in symbols[:2]
        )
        if status == "AMBIGUOUS"
        else (),
    )
    changed = relation.model_copy(
        update={
            "resolution": resolution,
            "source": EntityRef(id=symbols[0].id, entity_type=symbols[0].entity_type),
        }
    )
    batch = UcmBatch.model_construct(
        repository_id=REPO,
        entities=tuple(changed if e.id == relation.id else e for e in facts),
    )
    records = _records(batch, str)
    stored = [
        r
        for row in records
        for r in json.loads(row[5])["relations"]
        if r["id"] == relation.id
    ]
    assert stored and all(r["resolution"]["status"] == status for r in stored)
    assert all(
        r["resolution"]["target"] is None and r["certainty"] == relation.certainty
        for r in stored
    )
