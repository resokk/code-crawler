# MCP authentication and repository access

A02 adds mandatory bearer authentication to Streamable HTTP. No anonymous mode,
identity tool argument or trusted caller-supplied user header is supported.
Deploy behind TLS; plaintext HTTP is suitable only for loopback development.

`MCP_ACCESS_POLICY` is deployment-controlled JSON, required at startup:

```json
{"principals":[{"id":"client-a","token_sha256":"REPLACE_WITH_64_LOWERCASE_HEX_DIGITS","expires_at":2000000000,"repositories":["org/app"],"permissions":["read","evidence","source","discover"]}]}
```

Generate each bearer token from at least 32 random bytes. Store only its SHA-256
hex digest in policy; distribute the original token through your secret manager.
Send `Authorization: Bearer TOKEN` on every HTTP request. Policy must be configured
by the operator, never by the client. Restart to apply grants/revocations; all
workers must use the same policy. Expired tokens fail closed. Duplicate identities
or digests and malformed/unknown fields reject startup with generic diagnostics.
Never commit tokens, policy instances or production repository memberships.

Principal identity, explicit repository membership and operation permissions are
separate. `read` permits structural/lexical results including SQL and embedded
Evidence metadata. `evidence` permits get_evidence; `source` permits the authorized
library source-Evidence reader; `discover` permits global discovery. Cross-repository traversal requires both
`read` and `discover`, with membership and server scope for the root and every
repository in the supplied version context. Context IDs never grant access. There are no
wildcards or default grants. All operations still require repository membership.
Discovery additionally intersects membership with DISCOVERY_REPOSITORY_KEYS;
client repository_keys can only narrow the result, never broaden it.

Every MCP tool goes through the shared gate before acquiring the DB connection.
Missing/invalid credentials yield HTTP 401; repository/operation denials yield a
generic tool error, identical for unknown and forbidden repositories. Query errors
are redacted; no raw DB exceptions, source fragments or paths appear in errors.
Authentication and authorization decisions emit structured code_crawler.audit
logs containing principal ID, operation, result and hashed repository keys, never
bearer values, query arguments, source text or DB connection strings. The operator
must collect stderr into an access-restricted persistent log sink. These logs do
not replace an organization-wide durable audit service.

The server remains stateless: identity comes from the authenticated request;
immutable deployment policy is shared, user grants are not retained in sessions.
Direct in-process tool calls also fail closed without a verified request token.
Raw SQL, search functions, published_reader and source_evidence are privileged
library APIs for CLI/administrative jobs with database credentials, not a network
security boundary. Untrusted library callers must use authorized_evidence, which
checks repository and source permission before opening a reader. MCP exposes no
raw archived source endpoint. Database credentials themselves must remain trusted.

No UCM/schema migration or snapshot mutation is introduced. ACL configuration
is operator-managed deployment state; per-request database ACL changes and an
external OAuth issuer are outside this bounded bearer profile.
