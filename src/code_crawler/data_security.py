"""Bounded, versioned best-effort secret masking for derivative data only."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain
from typing import Literal
from uuid import UUID

VERSION = "source-security-v1"
MARKER = "[REDACTED]"
_NAMES = r"(?:api[_-]?(?:key|token)|password|passwd|secret|client[_-]?secret|access[_-]?token|token|aws_secret_access_key|aws_session_token)"
_PREFIX = rf"\b{_NAMES}\b[\"']?\s*[:=]\s*"
_PATTERNS = (
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?P<kind>(?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY)-----[\s\S]*?(?:-----END (?P=kind)-----|\Z)"
        ),
    ),
    (
        "CREDENTIAL_TOKEN",
        re.compile(
            r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})"
        ),
    ),
    (
        "BEARER",
        re.compile(r"\bBearer[ \t]+(?P<value>[A-Za-z0-9._~+/-]{1,}=*)", re.IGNORECASE),
    ),
    (
        "URL_CREDENTIAL",
        re.compile(
            r"\b[a-z][a-z0-9+.-]*://(?P<value>[^\s/:@]+:[^\s/@]+)@", re.IGNORECASE
        ),
    ),
    (
        "JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    (
        "SECRET_ASSIGNMENT",
        re.compile(_PREFIX + r'"(?P<value>(?:[^"\\\r\n]|\\.|"")*)"', re.IGNORECASE),
    ),
    (
        "SECRET_ASSIGNMENT",
        re.compile(_PREFIX + r"'(?P<value>(?:[^'\\\r\n]|\\.|'')*)'", re.IGNORECASE),
    ),
    (
        "SECRET_ASSIGNMENT",
        re.compile(_PREFIX + r"(?P<value>[^\s,;'\"{}\[\]()]{8,})", re.IGNORECASE),
    ),
)


_PUBLIC_KEYS = frozenset(
    {
        "id",
        "entity_id",
        "source_file_id",
        "repository_id",
        "snapshot_id",
        "generation_id",
        "content_sha256",
        "status",
        "certainty",
        "entity_type",
        "relation_kind",
        "parse_status",
        "source",
        "target",
        "resolution",
        "candidates",
        "evidence",
        "coverage",
        "source_range",
        "start",
        "end",
        "line",
        "byte_column",
        "policy_version",
        "content",
        "provenance",
        "relations",
        "redaction",
        "data_security",
        "title",
        "text",
        "summary",
        "path",
        "name",
        "target_language",
        "source_language",
        "redacted_source",
        "language",
        "items",
        "truncated",
    }
)


class DataSecurityError(ValueError):
    """Safe failure: no original value or caller policy exception is attached."""


def _candidate(value: str, minimum: int = 8) -> bool:
    return (
        len(value) >= minimum
        and value.lower()
        not in {
            MARKER.lower(),
            "your_api_key",
            "<token>",
        }
        and re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", value) is None
    )


def _spans(text: str, secret_field: bool = False) -> list[tuple[int, int, str]]:
    if len(text.encode("utf-8")) > 2 * 1024 * 1024:
        raise DataSecurityError("source data policy scan limit exceeded")
    spans = []
    if secret_field and _candidate(text, 1):
        if len(text.encode()) > 65536:
            raise DataSecurityError("source data policy span limit exceeded")
        spans.append((0, len(text), "SECRET_FIELD"))
    for category, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = (
                match.span("value") if "value" in pattern.groupindex else match.span()
            )
            if len(text[start:end].encode()) > 65536:
                raise DataSecurityError("source data policy span limit exceeded")
            if _candidate(
                text[start:end],
                1
                if category in {"SECRET_ASSIGNMENT", "URL_CREDENTIAL", "BEARER"}
                else 8,
            ):
                spans.append((start, end, category))
            if len(spans) > 256:
                raise DataSecurityError("source data policy finding limit exceeded")
    return sorted(set(spans))


def _strings(
    value: object, path: str = "$", depth: int = 0
) -> Iterator[tuple[str, str, bool]]:
    if depth > 64:
        raise DataSecurityError("source data policy depth limit exceeded")
    if isinstance(value, str):
        yield path, value, False
    elif isinstance(value, dict):
        for i, (key, child) in enumerate(value.items()):
            if not isinstance(key, str):
                raise DataSecurityError("source data policy requires string keys")
            yield f"{path}.k[{i}]", key, False
            if isinstance(child, str):
                yield (
                    f"{path}.v[{i}]",
                    child,
                    re.fullmatch(_NAMES, key, re.IGNORECASE) is not None,
                )
            else:
                yield from _strings(child, f"{path}.v[{i}]", depth + 1)
    elif isinstance(value, (list, tuple)):
        for i, child in enumerate(value):
            yield from _strings(child, f"{path}[{i}]", depth + 1)
    elif value is not None and not isinstance(value, (bool, int, float, UUID)):
        raise DataSecurityError("source data policy requires JSON data")


def structural_value(key: str, value: str) -> bool:
    """Recognize public protocol constants and canonical links, not source labels."""
    if key in {"status", "certainty", "entity_type", "relation_kind", "parse_status"}:
        return re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value) is not None
    if key in {
        "id",
        "entity_id",
        "source_file_id",
        "repository_id",
        "snapshot_id",
        "generation_id",
        "content_sha256",
    }:
        return (
            re.fullmatch(
                r"(?:(?:ucm:|doc:)?[0-9a-f]{64}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})",
                value,
            )
            is not None
        )
    return False


@dataclass(frozen=True)
class SecretPolicy:
    action: Literal["mask", "skip", "reject"] = "mask"

    def __post_init__(self) -> None:
        if self.action not in ("mask", "skip", "reject"):
            raise DataSecurityError("invalid source data policy action")

    @property
    def version(self) -> str:
        return f"{VERSION}:{self.action}"

    def clean(
        self, payload: object, *, context: object | None = None
    ) -> tuple[object | None, dict]:
        """Return derivative JSON and safe coordinates; never mutate the input."""
        findings = []
        known: set[str] = set()
        direct = {}
        total_bytes = 0
        fields = chain(
            _strings(payload),
            _strings(context, "$context") if context is not None else (),
        )
        for n, (path, text, is_secret) in enumerate(fields):
            if n > 100000:
                raise DataSecurityError("source data policy field limit exceeded")
            total_bytes += len(text.encode())
            if total_bytes > 16 * 1024 * 1024:
                raise DataSecurityError("source data policy payload limit exceeded")
            spans = _spans(text, is_secret)
            direct[path] = spans
            for start, end, category in spans:
                if end - start >= 8:
                    known.add(text[start:end])
                findings.append(
                    {
                        "field": path,
                        "category": category,
                        "start_byte": len(text[:start].encode()),
                        "end_byte": len(text[:end].encode()),
                    }
                )
                if len(findings) > 4096:
                    raise DataSecurityError("source data policy finding limit exceeded")
        report = {
            "policy_version": self.version,
            "status": "PARTIAL" if findings else "COMPLETE",
            "scope": "supported-detectors-only",
            "findings": findings,
        }
        if findings and self.action == "reject":
            error = DataSecurityError("source data rejected by security policy")
            error.report = report
            raise error
        if findings and self.action == "skip":
            return None, report
        if not findings:
            return payload, report
        values = sorted(known, key=lambda s: (-len(s), s))
        if total_bytes * len(values) > 128 * 1024 * 1024:
            raise DataSecurityError("source data policy replacement budget exceeded")
        replacements = 0

        def text_clean(text: str, path: str) -> str:
            nonlocal replacements
            spans = [(a, b) for a, b, _ in direct.get(path, ())]
            # Literal search avoids caching secret-bearing regular expressions globally.
            for value in values:
                start = 0
                while (found := text.find(value, start)) >= 0:
                    replacements += 1
                    if replacements > 4096:
                        raise DataSecurityError(
                            "source data policy replacement limit exceeded"
                        )
                    spans.append((found, found + len(value)))
                    start = found + 1
            merged = []
            for start, end in sorted(set(spans)):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            output, previous = [], 0
            for start, end in merged:
                output.extend((text[previous:start], MARKER))
                previous = end
            return "".join((*output, text[previous:]))

        def walk(value: object, path: str = "$", field: str = "") -> object:
            if isinstance(value, str):
                if not direct.get(path) and structural_value(field, value):
                    return value
                return text_clean(value, path)
            if isinstance(value, (tuple, list)):
                return [walk(child, f"{path}[{i}]") for i, child in enumerate(value)]
            if isinstance(value, dict):
                result = {}
                for i, (key, child) in enumerate(value.items()):
                    key_path = f"{path}.k[{i}]"
                    if key not in _PUBLIC_KEYS or direct.get(key_path):
                        key = text_clean(key, key_path)
                    if key in result:
                        raise DataSecurityError("redacted dictionary key collision")
                    result[key] = walk(child, f"{path}.v[{i}]", key)
                return result
            return value

        return walk(payload), report


DEFAULT_POLICY = SecretPolicy()


def embedding_input(content: dict) -> str:
    """Build future embedding input from sanitized C01 content, never raw source."""
    safe, _ = SecretPolicy().clean(content)
    return "\n".join(
        safe[key]
        for key in ("title", "summary", "redacted_source")
        if isinstance(safe.get(key), str)
    )
