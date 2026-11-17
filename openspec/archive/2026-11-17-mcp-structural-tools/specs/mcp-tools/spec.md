# MCP structural tools

## Requirement: tool set

GIVEN a running server WHEN tools are listed THEN the eight structural tools are
present, each with a description and typed arguments. (lexical-search-index later
adds search_text.)

## Requirement: published snapshots only

GIVEN a repository with a published snapshot WHEN a tool is called THEN it answers
from that snapshot inside a read-only transaction.

GIVEN an unknown repository or one without a publication WHEN a tool is called
THEN the call fails with a tool error naming the cause.

## Requirement: validated input

GIVEN a malformed entity ID, an empty repository key, or a limit or depth out of
range WHEN a tool is called THEN it is rejected before any query runs.

## Requirement: explicit incompleteness

GIVEN unresolved relations, truncated results or accesses without a proven
execution WHEN a tool returns THEN those are present and marked in the result
rather than omitted.
