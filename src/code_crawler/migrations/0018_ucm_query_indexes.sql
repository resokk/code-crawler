-- Indexes for the structural search queries (docs/structural-search.md); each one
-- replaces a full scan of a per-snapshot fact table measured with EXPLAIN ANALYZE.
CREATE INDEX ucm_entities_symbol_name_idx ON ucm_entities(snapshot_id, name)
    WHERE entity_type='SYMBOL';
CREATE INDEX ucm_relation_candidates_candidate_idx
    ON ucm_relation_candidates(snapshot_id, candidate_id);
CREATE INDEX ucm_sql_executions_owner_idx
    ON ucm_sql_executions(snapshot_id, owner_symbol_id);
CREATE INDEX ucm_sql_access_names_normalized_idx
    ON ucm_sql_access_names(snapshot_id, part, normalized);
