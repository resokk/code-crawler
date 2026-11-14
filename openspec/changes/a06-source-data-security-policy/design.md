# Design: Защита исходных байтов, секретов и поисковых проекций

## Context and current implementation
source blobs, SQL literals и будущие search_documents/embeddings потенциально содержат секреты, персональные данные и сведения о приватных репозиториях.

## Proposed solution
### Decision 1
Определить уровни данных raw source / evidence / search projection / embedding и правила доступа/retention.

### Decision 2
Разделить сохранение неизменённого оригинала для authorised evidence и redacted поисковый документ.

### Decision 3
Ввести консервативный secret detector с диагностикой и политикой reject/mask/skip без записи plaintext в logs.

### Decision 4
При срабатывании исключать опасные spans из search_documents и embedding input; сохранять provenance/coverage redaction.

### Decision 5
Применять tenant/repository scope ко всем производным данным и аудитам.

## Integration and compatibility
- Reuse canonical UCM entities, immutable published snapshots and existing migration/adapter contracts.
- Keep existing public APIs compatible unless this change explicitly requires a versioned extension.
- Do not resolve cross-repository links during ingestion; expose deferred candidates only at query time.
- Every inferred relationship must retain Resolution, Coverage and Evidence; do not promote UNKNOWN to STATIC_PROVEN.

## Alternatives and trade-offs
- Avoid a broad rewrite or introducing a parallel storage model; targeted updates are easier to verify and roll back.
- If an optimization weakens referential integrity or snapshot immutability, reject it and preserve the current behavior.

## Failure modes and recovery
- Fail closed for invalid input, unknown ownership or missing permissions; report diagnostics without leaking source bytes.
- Database modifications require migration, backward-compatibility review and integration tests on PostgreSQL 15.
- A failed operation MUST leave the previously published snapshot readable and unchanged.

## Implementation surfaces
src/code_crawler/source_evidence.py; src/code_crawler/search_documents.py; src/code_crawler/server.py; docs/source-evidence.md; docs/search-documents.md; tests/

## Dependencies
A02 для управления доступом; C01 для хранения документов
