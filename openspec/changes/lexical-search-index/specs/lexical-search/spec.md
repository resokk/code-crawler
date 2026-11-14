# Lexical search

## Requirement: normalized identifier matching

GIVEN symbols app.Repo.load and app.Service WHEN searching "LOAD" THEN
app.Repo.load is first with match EXACT.

GIVEN the query "repo load" WHEN searching THEN app.Repo.load is returned with
match WORDS.

GIVEN the misspelled query "Servce" WHEN searching THEN app.Service is returned
with match SIMILAR.

GIVEN a query unlike any name WHEN searching THEN no items are returned.

## Requirement: filters

GIVEN entity_types ["SOURCE_FILE"] WHEN searching THEN only source files are
returned, with their path.

GIVEN an entity type outside the searchable list, a blank query, or an offset
above 1000 WHEN searching THEN the call is rejected.

GIVEN a snapshot ID that was never published, or belongs to another repository
WHEN searching THEN the call is rejected.

## Requirement: deterministic pagination

GIVEN more results than limit WHEN searching THEN truncated is true and
next_offset points at the next page; fetching it continues the same order without
repeating items; the last page has next_offset null.

## Requirement: index-backed

GIVEN a snapshot with over 100k entities WHEN searching THEN the plan uses the GIN
indexes and does not scan ucm_entities sequentially.
