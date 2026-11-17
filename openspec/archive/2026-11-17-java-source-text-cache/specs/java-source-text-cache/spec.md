# Capability: java-source-text-cache

## ADDED Requirements

### Requirement: Scoped bounded decoding cache
Decoded Java node text MUST be cached only during a synchronous file operation.
Retained keys MUST prevent stale identity reuse. Cache capacity MUST be bounded
and saturation MUST preserve returned text.

#### Scenario: Repeated node
- GIVEN a live node is read repeatedly inside a file operation
- WHEN _text is called
- THEN its decoded text is reused, including an empty string

#### Scenario: Successive files
- GIVEN one worker processes several files
- WHEN one file finishes and the next starts
- THEN the previous cache is empty and no text from another tree is returned

### Requirement: Worker isolation and cleanup
Every worker MUST own its cache scope, and all retained Node/text references MUST
be released on both normal completion and errors.

#### Scenario: Parallel analysis
- GIVEN two workers analyze different Java files concurrently
- WHEN nodes are read and scopes end
- THEN their cache objects are distinct and both release all entries

#### Scenario: Failed analysis
- GIVEN text has been cached and extraction raises
- WHEN the operation unwinds
- THEN the worker slot is restored and retained cache entries are cleared

### Requirement: Preserve output semantics
Cached and uncached operation MUST return identical parse/UCM results, including
None, empty text, invalid UTF-8 replacement, evidence and partial reasons.

#### Scenario: Partial SQL and path limits
- GIVEN a file has partial SQL recovery and bounded paths
- WHEN cached and uncached analysis run
- THEN complete fact payloads and incompleteness reasons match

### Requirement: Measured performance
A reproducible benchmark MUST report hit/miss counts, wall time, peak RSS and full
fact digests, including workloads with little text reuse.

#### Scenario: Low reuse
- GIVEN a small file with few repeated reads
- WHEN caching is compared with direct decoding
- THEN any time or memory regression is reported rather than hidden
