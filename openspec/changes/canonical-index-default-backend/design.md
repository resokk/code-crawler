# Design

Dispatch index to canonical by default and delegate to index_registered(publish=True).
Share canonical CLI options with index-sources; keep its BUILDING default unchanged.
Resolve local paths without syncing; clone/pull remote repositories into identity-
qualified cache directories and verify origin. Use explicit repository keys where
provided; otherwise derive non-basename local/remote identities without URL credentials.

Keep the old writer callable as index_legacy and require explicit backend selection.
Reject canonical-only options for legacy and print its non-authoritative executes
semantics. Do not promote or copy legacy execution edges into canonical facts.

Test real local repositories, file:// bare remotes with clone/update, unchanged
reuse, malformed/parsing sources, schema readiness, publication failure and legacy
migration behavior against PostgreSQL 15. No database migrations or parser changes.
