# Canonical index publication CLI

Provide a complete opt-in canonical index → validate → publish user flow, plus
explicit validation/publication of existing snapshots. Reuse the atomic lifecycle
API and enforce expected-pointer CAS. Keep BUILDING-only indexing as default.
No parser, source evidence policy, backend default or storage changes.
