# Parallel snapshot preparation

Add opt-in --analysis-workers (1..32, default 1) for Java per-file analysis.
Use spawn processes with bounded work per existing source slice; preserve captured
bytes, catalogue identity, stable result order, typed facts and atomic publication.
Keep PostgreSQL, normalized row preparation, spool writing and non-Java adapters in
the parent. No AST/DB connection is serialized. Measure 1/2/4 workers and aggregate
process memory; catalogue copies/startup can outweigh CPU gains.
