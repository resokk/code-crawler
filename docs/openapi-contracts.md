# OpenAPI contract adapter (D05)

`OpenApiSourceAdapter` discovers OpenAPI 3.0/3.1/3.2 by the root `openapi`
field in captured UTF-8 YAML/JSON. It emits existing typed UCM Symbols, Values,
Relations and ExternalReferences; central ingestion owns persistence/publication.
Source execution is never inferred. Optional local Java bindings are described in
[openapi-java-bindings.md](openapi-java-bindings.md).

Inputs are bounded; unsafe YAML tags/aliases, duplicate keys,
path escapes and network reads are forbidden. References form edges rather than
recursive document expansion. Unknown semantics retain PARTIAL coverage.

## Representation and provenance

Migration `0025_openapi_contract_adapter.sql` extends `ucm_symbols.symbol_kind`
and the normalized relation registry. No parallel graph/tables are introduced.
Symbol kinds: OPENAPI_DOCUMENT, OPERATION, PARAMETER, SCHEMA, FIELD, RESPONSE,
BODY, MEDIA_TYPE, SECURITY, CALLBACK, WEBHOOK, ELEMENT (all with OPENAPI_ prefix).
The document root carries a `dialect` Value (exact declared version); referenced
schema fragment roots are OPENAPI_SCHEMA. Qualified name is `path#JSON-pointer`.
Logical IDs contain repository, source path, node pointer and role; they survive
content edits and cannot collide between repositories.

Every syntax node, including array entries and scalar fields, has a Symbol.
CONTAINS records the source tree. OPENAPI_ATTRIBUTE links to typed scalar Value
(string/number/bool/null), preserving schema type, required, nullable, composition,
discriminator, media types, security requirements, callbacks and extension data.
Empty objects/arrays remain syntax nodes; no source document is hidden in JSONB.
Each operation additionally carries direct `method` and `path` attributes. For
callback operations, path is the callback expression; for webhooks it is the name.
OpenAPI 3.2 `query`, `additionalOperations` and `in: querystring` are retained.

OPENAPI_REF connects local `$ref` targets and explicit discriminator mappings.
References do not expand their targets, so recursive/composed schemas stay finite.
Bare discriminator names resolve against components/schemas; JSON Pointer escapes
and percent-encoded fragments are decoded. Local `$anchor` is supported for 3.1+;
multiple matching anchors produce AMBIGUOUS with candidates and UNKNOWN certainty.
Missing targets produce UNRESOLVED, UNKNOWN and a diagnostic. RESOLVED,
STATIC_PROVEN proves an explicit contract syntax reference, never a runtime call,
implementation binding or cross-repository dependency.

Every Relation/ExternalReference has captured UTF-8 SourceRange and Evidence,
with analyzer/version/rule and PARTIAL Coverage. The canonical reader restores
source evidence from the archived bytes after publication. Examples/defaults/
enums/constants and vendor-extension payloads are retained as data; their `$ref`
strings are not interpreted as graph references.

## Discovery, references and incremental lifecycle

Root `openapi: 3.0.x`, `3.1.x` or `3.2.x` activates a document regardless of filename.
Other YAML/JSON files become contract facts only when transitively referenced by
an active document. Unrelated files receive metadata-only UNSUPPORTED reports.
Explicit unsupported openapi versions cannot be mistaken for schema fragments.
Relative refs use captured repository-relative POSIX paths; safe `../` within the
repository is supported. No ambient source read, URL fetch, DB connection or other
repository catalog is available to the producer. Remote URI/base-scope selectors
are ExternalReference(SymbolSelector `openapi.ref::<URI>`) with UNKNOWN certainty.
`$id` changes and dynamic scope keywords are preserved with diagnostics; refs under
`$id` remain deferred. Anchors under a separate `$id` scope are not guessed.

Direct file refs, including missing files, become incremental dependencies.
Reachable-file/dialect membership participates in prepared analysis_version:
adding/removing a root/ref that activates a previously metadata-only fragment
invalidates the OpenAPI scope. Ordinary content edits use file dependencies;
unchanged snapshots reuse the exact facts, reports and diagnostics. Java/SQL/TS
analysis is not duplicated. Producer failure preserves the current publication.

CLI `index` and `index-sources` enable OpenApiSourceAdapter for `.json/.yaml/.yml`.
Standalone programmatic use:

```python
AdapterRegistry((OpenApiSourceAdapter(),))
```

When combined with TypeScript, use `TypeScriptSourceAdapter(include_json=False)`
(as the CLI does). TypeScript's default remains compatible for standalone callers.
JS/TS prepare_inventory receives captured tsconfig.json regardless of the JSON
route owner; config dependencies still trigger reanalysis. No duplicate suffix
routing or content-dependent registry priority is introduced.

## Dialects, safety and limitations

This is a syntax/fact adapter, not a complete OpenAPI or JSON Schema validator.
3.0 nullable is retained as a 3.0 keyword. In 3.1/3.2 null is expressed through
JSON Schema types/composition; legacy nullable is retained with a diagnostic and
is not treated as a null union. Boolean schemas/type arrays, anchors and webhooks
in 3.0, and QUERY/additionalOperations/querystring before 3.2 have dialect
warnings. `$ref` siblings, composition, discriminator, required, defaults and
security are preserved without computing an effective validation schema or
runtime authorization. OAuth URLs, server templates, callbacks and webhooks are
never invoked. Local Java binding is provided by D06 through a frozen captured Java catalog;
[limits and evidence](openapi-java-bindings.md) remain explicit.

Parser budgets per file: 4 MiB, depth 64, 20,000 YAML scalar/collection events.
JSON must be strict (no duplicate keys/NaN/Infinity). YAML uses PyYAML's safe
syntax parser, without object construction; aliases, non-scalar/duplicate keys,
custom tags and multi-document streams are rejected. YAML 1.1 on/off/yes/no and
timestamps stay strings; only true/false become booleans. Supported input is
UTF-8 without BOM/NUL. Bad syntax/encoding/budgets yield INVALID_DOCUMENT,
UNSUPPORTED and no contract facts; an unrelated valid file is simply UNSUPPORTED.
Errors are per-file and cannot create a false COMPLETE analysis. Malformed typed
node shapes, invalid/missing refs, dialect mismatches, unknown extensions and
dynamic scope have structured diagnostics and retained PARTIAL facts.

Absolute/drive/backslash/NUL paths and decoded repository escapes are rejected;
reference query components are unsupported. Custom dialects, external `$id`
resource catalogs, dynamic reference evaluation, implicit discriminator matching,
YAML aliases/merge semantics, server expansion and actual HTTP bindings are not
claimed. JSON/YAML schema fragments must be in the captured routed inventory.

Conformance: `tests/test_openapi_adapter.py` and
`tests/integration/test_openapi_storage.py`: 3.0/3.1/3.2, recursive/local/relative/
remote/missing/ambiguous refs, discriminator mappings, dialect boundaries,
QUERY/querystring, unsafe parsing/paths, deterministic facts, published source
Evidence, incremental reuse/edit/delete/activation, repository isolation,
TypeScript config coexistence and producer-failure preservation on PostgreSQL 15.
