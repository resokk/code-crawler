"""Deployment-owned bearer identities, repository grants and redacted audit events."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Literal

import asyncpg
from fastmcp.server.auth import AccessToken, TokenVerifier
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    from code_crawler.reader import EvidenceFragment

Permission = Literal["read", "evidence", "source", "discover", "monitor"]
AUDIT = logging.getLogger("code_crawler.audit")


def configure_audit() -> None:
    """Keep decision events enabled even before any authenticated tool request."""
    if not AUDIT.handlers:
        AUDIT.addHandler(logging.StreamHandler())
    AUDIT.setLevel(logging.INFO)


def audit(
    principal: str | None,
    operation: str,
    allowed: bool,
    repositories: tuple[str, ...] = (),
) -> None:
    """Record decisions without credentials, query text or repository names."""
    AUDIT.info(
        json.dumps(
            {
                "event": "mcp_access",
                "principal": principal,
                "operation": operation,
                "allowed": allowed,
                "repositories": [
                    hashlib.sha256(k.encode()).hexdigest() for k in repositories
                ],
            },
            sort_keys=True,
        )
    )


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    expires_at: int = Field(gt=0, strict=True)
    repositories: tuple[str, ...] = Field(max_length=1000)
    permissions: frozenset[Permission]

    @field_validator("repositories")
    @classmethod
    def validate_keys(cls, keys: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(keys)) != len(keys) or any(
            not k or len(k) > 512 or "*" in k or any(ord(c) < 32 for c in k)
            for k in keys
        ):
            raise ValueError("invalid repository scope")
        return keys


class AccessPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    principals: tuple[Principal, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique(self) -> AccessPolicy:
        if len({p.id for p in self.principals}) != len(self.principals) or len(
            {p.token_sha256 for p in self.principals}
        ) != len(self.principals):
            raise ValueError("duplicate identity or credential")
        return self

    def authenticate(self, token: str | None) -> Principal:
        """Resolve a request credential against this policy, ignoring caller claims."""
        if (
            token
            and len(token) <= 4096
            and re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token) is not None
        ):
            digest = hashlib.sha256(token.encode()).hexdigest()
            for principal in self.principals:
                if (
                    hmac.compare_digest(principal.token_sha256, digest)
                    and principal.expires_at > time.time()
                ):
                    return principal
        audit(None, "authenticate", False)
        raise PermissionError("access denied")

    def authorize(
        self, principal: Principal, operation: Permission, repositories: tuple[str, ...]
    ) -> None:
        """Check operation and every requested membership before touching source data."""
        allowed = (
            principal in self.principals
            and principal.expires_at > time.time()
            and operation in principal.permissions
            and all(k in principal.repositories for k in repositories)
        )
        audit(principal.id, operation, allowed, repositories)
        if not allowed:
            raise PermissionError("access denied")


def load_policy() -> AccessPolicy:
    """Read trusted deployment configuration; never expose validation inputs."""
    try:
        raw = os.environ.get("MCP_ACCESS_POLICY", "")
        if not raw or len(raw) > 1024 * 1024:
            raise ValueError
        return AccessPolicy.model_validate_json(raw)
    except (ValueError, TypeError):
        raise RuntimeError("valid MCP_ACCESS_POLICY is required") from None


class PolicyVerifier(TokenVerifier):
    def get_middleware(self) -> list[Middleware]:
        """Audit transport-level rejection for every supported HTTP app entry point."""
        configure_audit()
        return [Middleware(AuthenticationAudit), *super().get_middleware()]

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify stateless bearer credentials using deployment-owned digests."""
        try:
            principal = load_policy().authenticate(token)
        except (PermissionError, RuntimeError):
            return None
        audit(principal.id, "authenticate", True)
        return AccessToken(
            token=token,
            client_id=principal.id,
            subject=principal.id,
            scopes=sorted(principal.permissions),
            expires_at=principal.expires_at,
        )


class AuthenticationAudit:
    """Audit HTTP authentication failures handled before MCP tool dispatch."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def record(message: dict) -> None:
            if message["type"] == "http.response.start" and message["status"] in (
                401,
                403,
            ):
                audit(None, "http_authenticate", False)
            await send(message)

        await self.app(scope, receive, record)


async def authorized_evidence(
    conn: asyncpg.Connection,
    policy: AccessPolicy,
    token: AccessToken | None,
    repository_key: str,
    entity_id: str,
) -> tuple[EvidenceFragment, ...]:
    """Restore source Evidence only after request credential and source grant checks."""
    from code_crawler.reader import published_reader

    principal = policy.authenticate(token.token if token else None)
    policy.authorize(principal, "source", (repository_key,))
    async with published_reader(conn, repository_key) as reader:
        return await reader.get_evidence(entity_id)
