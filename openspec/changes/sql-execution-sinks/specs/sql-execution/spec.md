# Requirements

- Construction/preparation alone MUST NOT create SQL_EXECUTE or EXECUTES_SQL.
- Supported typed JDBC/Spring invocation MUST create a distinct execution site.
- Same-named custom APIs and unsupported receivers MUST NOT be promoted to sinks.
- Execution MUST own a CALL operation and ordered Values with exact source ranges.
- Prepared origin MUST be captured at preparation, independently of later SQL reassignment.
- Local aliases/scopes MUST be distinguished; overwrite/close/escape MUST invalidate origins.
- Unknown origins/batch queues MUST remain unresolved; branches MUST preserve candidates.
- Execution facts MUST carry Evidence/Resolution/Certainty/Coverage via relations.
- Storage MUST roundtrip facts, reject invalid CALL links and freeze published snapshots.
- Incremental no-change reuse MUST preserve equivalent execution facts.
