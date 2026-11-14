# Proposal: Хранение версионированных поисковых документов

## Why
Существует search_documents.project(), но документы не сохраняются и не участвуют в published-generation lifecycle.

## Outcome
Хранение версионированных поисковых документов. Создать search_documents и search_index_generations с (repository,snapshot,generation,entity_id,document_type,content,hash,provenance). Обеспечить deterministic projection: одинаковые UCM facts + версия генератора дают одинаковые hashes и doc identity. Публиковать generation атомарно и не показывать incomplete batches; поддержать reindex search без изменения UCM snapshot. Разделить target-language/summary и redacted source; учитывать secret policy и ACL по repository.

## Scope
- Создать search_documents и search_index_generations с (repository,snapshot,generation,entity_id,document_type,content,hash,provenance).
- Обеспечить deterministic projection: одинаковые UCM facts + версия генератора дают одинаковые hashes и doc identity.
- Публиковать generation атомарно и не показывать incomplete batches; поддержать reindex search без изменения UCM snapshot.
- Разделить target-language/summary и redacted source; учитывать secret policy и ACL по repository.

## Non-goals
Не менять канонические UCM факты при перерасчёте поисковых документов.

## Dependencies
A06 желательно; B02

## Impacted code
src/code_crawler/search_documents.py; src/code_crawler/migrations/; src/code_crawler/publication.py; tests/integration/; docs/search-documents.md

## Priority
P1
