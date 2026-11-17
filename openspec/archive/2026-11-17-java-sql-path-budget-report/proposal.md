# Configurable Java SQL path budget and overflow report

Expose the existing path-state budget through canonical CLI/Java adapter options,
default 256. Optionally export JSONL metadata for callable recovery that actually
truncates paths. Report metadata identifies code locations without source/SQL text.

Budget changes invalidate affected Java facts; diagnostics destinations do not.
Keep existing partial/truncation semantics, snapshot lifecycle and adapter isolation.
Reports cover methods reanalyzed in this run; incremental reuse must remain explicit.
