# Completion: C11 BPMN worker discovery

Implementation: `7c2204f29093df9ad23e555dc01173bd8a48c266` (shared C10/C11 projector upgrade).

Baseline: D02 exported supported Java handlers in a local preparation catalog and
bound BPMN tasks to canonical Methods, but repositories without BPMN XML had no
persisted worker registrations and C02/C04 reported worker declarations as
UNSUPPORTED. C11 persists only supported WORKER registrations from that same D02
catalog, independently of XML presence. It never promotes task references, beans,
delegate-name similarity, wrong handler signatures, disabled/abstract/static
workers or dynamic placeholders to definitions.

Forward migration 0032 adds BPMN_WORKER Symbols and BPMN_WORKER_HANDLER
(worker → canonical Method) to the typed registry. Annotation and method/contract
Evidence are retained on that relation; BPMN_ATTRIBUTE stores literal engine and
worker_type. Existing XML BPMN_HANDLER resolution and endpoint semantics are
unchanged. Java analysis fingerprints include worker/1 and the existing catalog
hash; projects without worker annotation markers avoid additional catalog building.
Old Java snapshots must be reindexed to obtain these new canonical facts; refresh
alone does not invent declarations from old prepared catalogs.

Discovery/3 projects `[worker_type]` with exact engine, handler_id and nullable
namespace/service qualifiers. Unknown deployment namespace/service is not inferred
from packages or repository names. C04 resolver/3 requires D02 engine provenance
from source Evidence, returns optional handler_id, and searches only explicitly
selected authorized C03 generations. Multiple declarations stay AMBIGUOUS; a
unique declaration stays PARTIAL and does not prove registration activation,
job execution or a runtime cross-repository relation. C05 cache generation and
algorithm identity are reused without introducing request-time writes.

CI tested `0b8b5e250fe1b73a5dd488f672fef24bd9fb8fdf`, a documentation-only
descendant containing the exact implementation above.

Validation:

- Local complete mandatory PG15 suite: 1509 passed (437.10 s), followed by all
  final resource/selector cases including the additionally added Camunda 7 case:
  34 passed. Ruff check, format check and git diff check passed.
- CI: 1510 passed; clean PostgreSQL 15 migrations, lint/format and generated
  file/working-tree checks passed.
- https://github.com/resokk/code-crawler/actions/runs/44181302582
- Typed source-task/remote-worker fixtures cover standalone Java workers,
  annotation + method Evidence, two-handler ambiguity, source-only exclusion,
  disabled/dynamic workers, Camunda 7 contract validation and Camunda 7/8 engine
  separation, authorization, bounded fanout, cache reuse, selected old snapshots,
  rename and publication rollback. Common projector cancellation/rollback is
  exercised by the shared Kafka projection failure scenario.
- No performance claim or unrelated optimization is included.

Contracts and operational limits: [global-discovery-catalog.md](../../../docs/global-discovery-catalog.md),
[external-reference-candidates.md](../../../docs/external-reference-candidates.md),
[bpmn-java-bindings.md](../../../docs/bpmn-java-bindings.md).
