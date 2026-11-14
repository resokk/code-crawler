# Requirements

- SQL statements MUST remain separate, with original decoded text ranges.
- Explicit dialect profile MUST preserve original quoted names and normalized parts.
- Effects MUST distinguish DML targets, sources, predicate reads and written columns.
- CTE/derived aliases MUST NOT become guessed physical database objects.
- Unknown/ambiguous names and wildcard expansion MUST retain explicit statuses/reasons.
- Dynamic/partial constructions MUST NOT assert semantic accesses.
- Parse errors/unsupported syntax MUST remain statement facts without fabricated effects.
- Execution links MUST originate from recognized construction resolution.
- Unused SQL MUST retain semantic facts without execution assertion.
- Normalized storage MUST roundtrip names/reasons and enforce immutable publication.
- Incremental profiles MUST invalidate dialect/SQLGlot changes and preserve unchanged facts.
