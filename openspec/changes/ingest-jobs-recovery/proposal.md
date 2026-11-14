# Ingest jobs recovery

A failed or killed index run left no record of what ran, where it stopped or why,
and its BUILDING snapshot stayed forever. Add persistent job state (stage, attempt,
failure diagnostics), a safe retry, cleanup of abandoned BUILDING snapshots and an
explicit retention command for old RETIRED versions. Analysis, validation and
publication semantics do not change.
