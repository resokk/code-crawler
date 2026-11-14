# Canonical reads

## Requirement: published snapshot scope

### Scenario: compound read during publication
GIVEN a published reader WHEN another connection publishes/retires/collects a version
THEN all reader queries remain scoped to the originally selected snapshot.

### Scenario: unknown or unpublished input
GIVEN no publication or a foreign/missing ID WHEN reading THEN a ValueError is
returned without reading BUILDING/READY data or selecting another snapshot.

## Requirement: full typed facts

### Scenario: direct reads and bounded relations
GIVEN published facts WHEN entity/SQL statement/access/binding is read THEN its
complete UCM model is returned with exact normalized details. Relation pages retain
uncertain candidates and limit/truncation, including incoming candidate links.

## Requirement: verified evidence

### Scenario: archived bytes
GIVEN Relation/ExternalReference Evidence WHEN retrieved THEN its exact SourceRange
bytes and SHA/provenance come from the same snapshot archive without filesystem IO.

### Scenario: historical unavailability or integrity failure
GIVEN a legacy missing archive WHEN reading proofs THEN unavailability is explicit;
GIVEN hash/range corruption THEN retrieval fails, never fabricates evidence.

### Scenario: context closure
GIVEN a closed reader WHEN any method is called THEN it refuses database access.
