# Incremental invalidation

## Requirement: adapter changes are scoped

GIVEN a published snapshot with adapter fingerprints WHEN one adapter's version or
catalog changes THEN only files routed to that adapter and their transitive
dependents are re-analyzed, and the plan is not a full rebuild.

GIVEN a file of another language that depends on a re-analyzed file WHEN planning
THEN it is re-analyzed too; files without such a dependency are reused.

## Requirement: facts are not reused without proof

GIVEN a baseline snapshot without adapter fingerprints WHEN the profile changes
THEN all supported files are re-analyzed.

GIVEN an adapter that is new to the baseline WHEN planning THEN all its files are
analyzed.

## Requirement: one snapshot

GIVEN several adapters WHEN indexing succeeds THEN one snapshot holds all facts and
one fingerprint row per adapter.
