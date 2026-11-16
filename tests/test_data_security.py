import hashlib
import json

import pytest
from test_search_documents import entities
from test_source_adapters import REPO

from code_crawler.data_security import (
    MARKER,
    DataSecurityError,
    SecretPolicy,
    embedding_input,
)
from code_crawler.ingestion import UcmBatch
from code_crawler.search_documents import project
from code_crawler.search_storage import _records
from code_crawler.ucm import Relation, SqlStatement

TOKEN = "ghp_" + "testOnlyCredentialValue123456789012345678"


@pytest.mark.parametrize(
    "value,secret",
    [
        (TOKEN, TOKEN),
        (
            'String apiToken = "test-only-sensitive-credential";',
            "test-only-sensitive-credential",
        ),
        ("password='x'", "x"),
        ("password='don''t-expose-this'", "don''t-expose-this"),
        ('password="escaped\\"credential-value"', 'escaped\\"credential-value'),
        ("Bearer opaque-test-credential", "opaque-test-credential"),
        ("Bearer x", "x"),
        ("postgresql://x:y@host/db", "x:y"),
        ("postgresql://user:secret@host/db", "user:secret"),
        (
            "-----BEGIN PRIVATE KEY-----\nonly-test-key-material\n-----END PRIVATE KEY-----",
            "only-test-key-material",
        ),
        ("AKIA1234567890ABCDEFGHIJ"[:20], "AKIA1234567890ABCDEFGHIJ"[:20]),
        (
            "-----BEGIN PRIVATE KEY-----\ntruncated-test-material",
            "truncated-test-material",
        ),
    ],
)
def test_detector_masks_supported_patterns_with_safe_offsets(value, secret):
    safe, report = SecretPolicy().clean({"value": value})
    assert secret not in safe["value"]
    assert MARKER in safe["value"]
    assert report["status"] == "PARTIAL"
    assert report["findings"]
    assert secret not in json.dumps(report) if len(secret) > 4 else True
    assert all(f["start_byte"] < f["end_byte"] for f in report["findings"])
    assert SecretPolicy().clean(safe)[0] == safe


def test_false_positives_utf8_and_duplicate_values():
    safe, report = SecretPolicy().clean(
        {
            "text": 'password = "${PASSWORD}"; getPassword(); token_count=123',
            "hash": "a" * 64,
        }
    )
    assert report["status"] == "COMPLETE"
    assert (
        SecretPolicy().clean("task-send-a-long-business-notification")[1]["status"]
        == "COMPLETE"
    )
    assert safe["text"].startswith('password = "${PASSWORD}"')
    value = 'пароль: password="sensitive-test-credential"'
    original = {"text": value, "copy": "sensitive-test-credential"}
    safe, report = SecretPolicy().clean(original)
    assert original["copy"] == "sensitive-test-credential"
    assert safe["copy"] == MARKER
    assert report["findings"][0]["start_byte"] == len('пароль: password="'.encode())
    assert SecretPolicy().clean({"password": "x", "context": "x"})[0] == {
        "password": MARKER,
        "context": "x",
    }


def test_reject_skip_and_scan_limits():
    assert SecretPolicy("skip").clean(TOKEN)[0] is None
    with pytest.raises(DataSecurityError) as error:
        SecretPolicy("reject").clean(TOKEN)
    assert TOKEN not in str(error.value)
    assert error.value.report["findings"]
    with pytest.raises(DataSecurityError, match="limit"):
        SecretPolicy().clean("x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(DataSecurityError, match="limit"):
        SecretPolicy().clean(" ".join([TOKEN] * 257))
    with pytest.raises(DataSecurityError, match="limit"):
        SecretPolicy().clean(TOKEN + "a" * 65536)
    with pytest.raises(DataSecurityError, match="limit"):
        SecretPolicy().clean({"password": "a" * 65537})
    with pytest.raises(DataSecurityError, match="invalid"):
        SecretPolicy("unsafe")


def secret_entities():
    return tuple(
        e.model_copy(
            update={"text": f"SELECT '{TOKEN}' FROM users", "reasons": (TOKEN,)}
        )
        if isinstance(e, SqlStatement)
        else e.model_copy(
            update={
                "evidence": tuple(
                    ev.model_copy(update={"description": TOKEN}) for ev in e.evidence
                )
            }
        )
        if isinstance(e, Relation)
        else e
        for e in entities()
    )


def test_projection_storage_embedding_provenance_and_modes():
    facts = secret_entities()
    raw = json.dumps([e.model_dump(mode="json") for e in facts])
    assert TOKEN in raw
    docs = list(project(facts))
    assert TOKEN not in json.dumps([d.model_dump(mode="json") for d in docs])
    assert any(d.redaction["status"] == "PARTIAL" for d in docs)
    batch = UcmBatch.model_construct(repository_id=REPO, entities=facts)
    rows = _records(batch, str)
    assert TOKEN not in json.dumps(rows)
    assert rows == _records(
        UcmBatch.model_construct(repository_id=REPO, entities=tuple(reversed(facts))),
        str,
    )
    for row in rows:
        assert TOKEN not in embedding_input(json.loads(row[3]))
        assert row[4] == hashlib.sha256(row[3].encode()).hexdigest()
    report = {}
    skipped = _records(batch, str, security_policy=SecretPolicy("skip"), report=report)
    assert len(skipped) < len(rows) and report["skipped_documents"] > 0
    assert report["status"] == "PARTIAL"
    assert TOKEN not in json.dumps(report)
    with pytest.raises(DataSecurityError):
        _records(batch, str, security_policy=SecretPolicy("reject"))
    assert raw == json.dumps([e.model_dump(mode="json") for e in facts])


def test_caller_cannot_opt_out_or_leak_through_failure():
    batch = UcmBatch.model_construct(repository_id=REPO, entities=secret_entities())

    def strip_label(text):
        return text.replace("password=", "")

    assert TOKEN not in json.dumps(_records(batch, strip_label))

    def fail(text):
        raise RuntimeError(TOKEN)

    with pytest.raises(DataSecurityError) as error:
        _records(batch, fail)
    assert TOKEN not in str(error.value)

    def inject(text):
        return text.replace("SELECT", "SELECT " + TOKEN)

    assert TOKEN not in json.dumps(_records(batch, inject))


def test_redaction_preserves_machine_certainty_and_ids():
    payload = {
        "text": "password='UNRESOLVED'",
        "status": "UNRESOLVED",
        "certainty": "INFERRED",
    }
    safe, report = SecretPolicy().clean(payload)
    assert safe["status"] == "UNRESOLVED" and MARKER in safe["text"]
    assert report["status"] == "PARTIAL"
    batch = UcmBatch.model_construct(repository_id=REPO, entities=secret_entities())
    with pytest.raises(DataSecurityError, match="structural fact"):
        _records(batch, lambda text: text.replace("PARTIAL", "RESOLVED"))


def test_callback_cannot_reinsert_a_known_unlabelled_value():
    secret = "test-only-sensitive-unprefixed-value"
    facts = tuple(
        e.model_copy(update={"text": f"SELECT x FROM users WHERE password='{secret}'"})
        if isinstance(e, SqlStatement)
        else e
        for e in entities()
    )
    batch = UcmBatch.model_construct(repository_id=REPO, entities=facts)

    def attempt(text):
        return text.replace("password", "opaque").replace(MARKER, secret)

    assert secret not in json.dumps(_records(batch, attempt))


def test_public_keys_remain_stable_and_dynamic_secret_keys_are_masked():
    payload = {
        "text": "password='entity_id'",
        "entity_id": "ucm:" + "a" * 64,
        TOKEN: "value",
    }
    safe, report = SecretPolicy().clean(payload)
    assert safe["entity_id"] == payload["entity_id"]
    assert TOKEN not in json.dumps(safe)
    assert MARKER in safe["text"] and MARKER in safe
    assert report["status"] == "PARTIAL"


def test_sql_title_does_not_leak_truncated_credential_prefix():
    facts = tuple(
        e.model_copy(
            update={"text": "SELECT '" + "padding" * 8 + TOKEN + "' FROM users"}
        )
        if isinstance(e, SqlStatement)
        else e
        for e in entities()
    )
    statement = next(d for d in project(facts) if d.kind == "SQL_STATEMENT")
    assert TOKEN[:12] not in statement.title
    assert TOKEN not in statement.text
