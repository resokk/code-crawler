CREATE TABLE search_discovery_generations (
    snapshot_id uuid PRIMARY KEY REFERENCES ucm_snapshots(id) ON DELETE CASCADE,
    repository_id uuid NOT NULL,
    generation uuid NOT NULL UNIQUE,
    projector_version text NOT NULL,
    coverage jsonb NOT NULL,
    FOREIGN KEY(repository_id,snapshot_id) REFERENCES ucm_snapshots(repository_id,id) ON DELETE CASCADE,
    UNIQUE(snapshot_id,generation)
);
CREATE TABLE search_discovery_entries (
    snapshot_id uuid NOT NULL,
    generation uuid NOT NULL,
    repository_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL,
    kind text NOT NULL,
    lookup_key jsonb NOT NULL,
    qualifier jsonb NOT NULL,
    source_file_id text,
    start_line integer,
    start_byte_column integer,
    end_line integer,
    end_byte_column integer,
    rule text NOT NULL,
    PRIMARY KEY(generation,entity_id,kind),
    FOREIGN KEY(snapshot_id,generation) REFERENCES search_discovery_generations(snapshot_id,generation) ON DELETE CASCADE,
    FOREIGN KEY(repository_id,snapshot_id) REFERENCES ucm_snapshots(repository_id,id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES ucm_entities(snapshot_id,entity_id,entity_type) ON DELETE CASCADE
);
CREATE INDEX search_discovery_lookup_idx ON search_discovery_entries(kind,md5(lookup_key::text),snapshot_id);
CREATE INDEX search_discovery_snapshot_idx ON search_discovery_entries(snapshot_id);
