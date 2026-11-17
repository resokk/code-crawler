# Design: BPMN worker definition discovery

## Starting point
D02 extracts Camunda/Flowable worker/delegate bindings and explicit external worker selectors, but discovery currently labels BPMN_WORKER UNSUPPORTED; users cannot find cross-repository worker declarations even when a typed handler is available.

## Decisions and integration
### D1
Enumerate D02 source facts and distinguish an actual supported worker handler DECLARATION from a BPMN task referring to a worker key.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D2
Define exact identity keys including engine/profile, worker type or topic, namespace/service when known and source snapshot; preserve missing deployment/activation as PARTIAL.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D3
Extend C02 projector and C04 lookup for worker definitions only; reject incomplete keys as definitive match and retain ambiguity among multiple handlers.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D4
Reuse selected C03 versions, immutable generations, retention pins and C05 cache invalidation; do not insert cross-repository UCM relations.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D5
Add BPMN task in repo A plus worker handler in repo B test and cases of two handlers, config expressions, no worker implementation, unauthorized repo.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

## Data lifecycle
Treat UCM snapshots as immutable. Derived discovery/search generations may be rebuilt independently and must remain consistently pinned within one read-only REPEATABLE READ transaction. Selection of other repositories happens only in a trusted version context at query time, not ingestion.

## Security and failure modes
Untrusted source/configuration is never executed. Bounded budgets for memory, candidates and query time. Enforce repository grants before SQL; no source secrets in search projections, diagnostics or logs. On failures the current publication and previous derived generation remain readable.

## Compatibility
Do not break existing C01–C06 API signatures without an explicitly versioned migration and regression tests. Only introduce schema migration if strictly required. Existing migration files are immutable.

## Relevant code
src/code_crawler/discovery.py; src/code_crawler/external_candidates.py; src/code_crawler/bpmn_bindings.py; src/code_crawler/bpmn_java_catalog.py; tests/integration/test_discovery_catalog_extended.py; tests/integration/test_bpmn_java_storage.py; docs/global-discovery-catalog.md; docs/bpmn-java-bindings.md
