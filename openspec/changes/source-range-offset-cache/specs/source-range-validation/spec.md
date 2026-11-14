# Source range validation

## Requirement: line boundaries are computed once per file

GIVEN one captured file and any number of ranges pointing into it WHEN adapter
results are validated THEN its line boundaries are scanned exactly once.

## Requirement: byte coordinates are bounded

GIVEN a position beyond the last line, or beyond the end of its line WHEN validated
THEN the adapter result is rejected with an AdapterError before ingestion.

GIVEN a position inside a multi-byte UTF-8 character WHEN validated THEN the
adapter result is rejected.

GIVEN a position at the end of a line or at the end of the file WHEN validated
THEN it is accepted.
