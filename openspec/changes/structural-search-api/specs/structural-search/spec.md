# Structural search

## Requirement: published scope and bounded results

GIVEN a repository without a published snapshot WHEN any query runs THEN it fails
with an error instead of reading unpublished facts.

GIVEN more matches than `limit` WHEN a query runs THEN `limit` items are returned
with `truncated` true.

GIVEN a limit outside 1..200 or a depth outside 1..6 WHEN a query runs THEN it is
rejected.

## Requirement: symbol search

GIVEN a simple or qualified name WHEN searching THEN symbols with exactly that name
are returned with kind, parameter types and source location.

GIVEN a kind or parameter type list that does not match WHEN searching THEN the
symbol is not returned.

## Requirement: calls keep uncertainty

GIVEN a resolved call WHEN callers or callees are requested THEN the relation is
returned with both endpoints, certainty, Coverage with reasons and Evidence.

GIVEN a call without a target in the repository WHEN callees are requested THEN it
is returned as UNRESOLVED with its reason and a null target.

## Requirement: SQL executions and table access

GIVEN a method executing SQL WHEN executions are requested for it THEN the sink,
its API and the executed statement text and operation are returned.

GIVEN statements reading and updating a table WHEN readers and writers are
requested THEN each access is returned with its statement and the executing
symbols; a column filter returns only column-level accesses of that column.

## Requirement: bounded traversal

GIVEN a call chain WHEN traced outward to depth N THEN relations up to distance N
are returned with their depth, and none beyond.

GIVEN direction "in" WHEN traced THEN relations pointing at the entity are followed.

## Requirement: evidence lookup

GIVEN a relation ID WHEN evidence is requested THEN the relation with Evidence,
Coverage and candidates is returned; an unknown ID is an error.
