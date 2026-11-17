# Design

Default 1 preserves existing to_thread analysis. Java prepared adapters lazily own
spawned processes for selected files only. Each child builds one read-only catalogue
from the same captured SourceInput bytes/config and verifies the bound analysis
version against the parent. Nodes/trees, connections, report sinks and callbacks
are never transferred. Each child receives path-only tasks against its catalogue
and returns typed FileAnalysis and numeric/metadata method observations over a
private pipe. IPC pickle is private process traffic, never an external file/API.

At most one request per process runs in the current existing source slice (64
files); no repository-wide result queue or prefetch is created. Contiguous groups
and ordered collection preserve file/fact/report order. Main-thread async execution
only coordinates; blocking IPC and shutdown use to_thread. Worker count does not
change analysis versions/facts or invalidate incremental reuse. The CLI job stores
workers for retry. Symbols/parser fallback and non-Java analysis remain sequential.

HTTP/BPMN/Kafka enrichment and validation remain in the parent using its original
catalogue. SQL path report callbacks are recreated as child-local collectors and
replayed into the parent sink; open file objects never cross processes.

Public multiprocessing Process/Pipe/sentinel APIs avoid unbounded initializer
respawn and detect abrupt worker death. Error/cancellation terminates the group,
joins/kills remaining processes and closes pipes. Source registry cleanup delegates
to managed adapters; an explicit incremental preparation-complete callback releases
workers before DB writes. Finally cleanup covers failures before completion.

A process group owns N additional full catalogues. Startup, imports, serialization,
parent normalization and write latency remain costs; this is not shared-memory
streaming or a promise of linear speedup. Keep default 1 pending real workloads.
