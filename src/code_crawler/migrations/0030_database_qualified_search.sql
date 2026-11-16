-- Exact physical access queries start with database/version and stored identifier spelling.
CREATE INDEX ucm_database_objects_search_idx ON public.ucm_database_objects
    (snapshot_id, database_key, version_key, table_name, schema_name, column_name, object_key);
