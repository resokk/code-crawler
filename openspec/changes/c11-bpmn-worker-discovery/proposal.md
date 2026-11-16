# Proposal: BPMN worker definition discovery

**Priority:** P1

## Problem
D02 extracts Camunda/Flowable worker/delegate bindings and explicit external worker selectors, but discovery currently labels BPMN_WORKER UNSUPPORTED; users cannot find cross-repository worker declarations even when a typed handler is available.

## Goal
Enumerate D02 source facts and distinguish an actual supported worker handler DECLARATION from a BPMN task referring to a worker key.

## Scope
- Enumerate D02 source facts and distinguish an actual supported worker handler DECLARATION from a BPMN task referring to a worker key.
- Define exact identity keys including engine/profile, worker type or topic, namespace/service when known and source snapshot; preserve missing deployment/activation as PARTIAL.
- Extend C02 projector and C04 lookup for worker definitions only; reject incomplete keys as definitive match and retain ambiguity among multiple handlers.
- Reuse selected C03 versions, immutable generations, retention pins and C05 cache invalidation; do not insert cross-repository UCM relations.
- Add BPMN task in repo A plus worker handler in repo B test and cases of two handlers, config expressions, no worker implementation, unauthorized repo.

## Non-goals
- Do not claim a task was executed or a worker process was running.
- Do not convert arbitrary Spring bean with similar name to a BPMN worker declaration.
- Do not change D01/D02 local handler semantics merely to enable search.

## Dependencies
C02, C04 and D02; C03 version contexts.

## Touched files
src/code_crawler/discovery.py; src/code_crawler/external_candidates.py; src/code_crawler/bpmn_bindings.py; src/code_crawler/bpmn_java_catalog.py; tests/integration/test_discovery_catalog_extended.py; tests/integration/test_bpmn_java_storage.py; docs/global-discovery-catalog.md; docs/bpmn-java-bindings.md

## Risks
- Inferred name matches must not become definite runtime dependencies.
- New storage data must be versioned and derived from immutable published UCM; do not reindex other repositories.
- Failed generation or resolver request must never alter a previously published snapshot or visible generation.
