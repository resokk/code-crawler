# Capability: search-document-persistence

## ADDED Requirements

### Requirement: Повторная проекция
The system MUST implement: Создать search_documents и search_index_generations с (repository,snapshot,generation,entity_id,document_type,content,hash,provenance).

#### Scenario: Повторная проекция
- GIVEN тот же snapshot и версия projection
- WHEN rebuild
- THEN hashes/число search documents одинаковы.

### Requirement: Атомарная видимость
The system MUST implement: Обеспечить deterministic projection: одинаковые UCM facts + версия генератора дают одинаковые hashes и doc identity.

#### Scenario: Атомарная видимость
- GIVEN построение generation прервано
- WHEN читатель ищет
- THEN он видит только предыдущую полную generation.

### Requirement: Provenance
The system MUST implement: Публиковать generation атомарно и не показывать incomplete batches; поддержать reindex search без изменения UCM snapshot.

#### Scenario: Provenance
- GIVEN документ создан из ORM/SQL/symbol
- WHEN его открывают
- THEN есть source UCM entity и snapshot.

### Requirement: Scope
The system MUST implement: Разделить target-language/summary и redacted source; учитывать secret policy и ACL по repository.

#### Scenario: Scope
- GIVEN запрос repo A
- WHEN ищут документы
- THEN документы repo B и чужие версии не возвращаются.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
