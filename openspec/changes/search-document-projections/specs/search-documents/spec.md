# Search documents

## Requirement: fact-only documents

GIVEN a method with a JDBC query WHEN projected THEN a SYMBOL document states its
kind, qualified signature, language and file range, and a SQL_STATEMENT document
states the SQL text, table and column accesses and the executing method with the
relation's certainty.

GIVEN a call to a target outside the repository WHEN projected THEN the call
summary counts it as unresolved with its reason and does not name a target.

GIVEN an SQL statement with no execution relation WHEN projected THEN the document
says no execution fact is recorded.

## Requirement: all adapters

GIVEN a Groovy class WHEN projected THEN it gets a SYMBOL document tagged with
language groovy.

## Requirement: database objects

GIVEN a database table object WHEN projected THEN its document holds the kind,
qualified name, database key and version.

## Requirement: determinism

GIVEN the same entities in a different order WHEN projected THEN the documents are
identical, IDs are unique, and content_sha256 matches the title and text.
