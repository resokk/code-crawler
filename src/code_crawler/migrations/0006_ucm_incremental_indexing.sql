CREATE TABLE public.ingest_snapshot_profiles (
    snapshot_id uuid PRIMARY KEY REFERENCES public.ucm_snapshots(id),
    analysis_version text NOT NULL CHECK (analysis_version ~ '\S'),
    profile_sha256 text NOT NULL CHECK (profile_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE TABLE public.ingest_file_entities (
    snapshot_id uuid NOT NULL,
    path text NOT NULL,
    entity_id text NOT NULL,
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,path) REFERENCES public.ucm_source_files(snapshot_id,path)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (snapshot_id,entity_id) REFERENCES public.ucm_entities(snapshot_id,entity_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX ingest_file_entities_path_idx ON public.ingest_file_entities(snapshot_id,path);
CREATE TABLE public.ingest_file_dependencies (
    snapshot_id uuid NOT NULL,
    dependent_path text NOT NULL,
    dependency_path text NOT NULL CHECK (
        dependency_path ~ '\S' AND dependency_path !~ '(^/|(^|/)\.\.?(/|$)|//|/$|[:\\])'
    ),
    PRIMARY KEY (snapshot_id,dependent_path,dependency_path),
    CHECK (dependent_path <> dependency_path),
    FOREIGN KEY (snapshot_id,dependent_path) REFERENCES public.ucm_source_files(snapshot_id,path)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX ingest_file_dependencies_reverse_idx
    ON public.ingest_file_dependencies(snapshot_id,dependency_path);

CREATE TRIGGER ingest_snapshot_profiles_write_guard BEFORE INSERT OR UPDATE OR DELETE
    ON public.ingest_snapshot_profiles FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_snapshot_profiles_truncate_guard BEFORE TRUNCATE
    ON public.ingest_snapshot_profiles FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_file_entities_write_guard BEFORE INSERT OR UPDATE OR DELETE
    ON public.ingest_file_entities FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_file_entities_truncate_guard BEFORE TRUNCATE
    ON public.ingest_file_entities FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_file_dependencies_write_guard BEFORE INSERT OR UPDATE OR DELETE
    ON public.ingest_file_dependencies FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_file_dependencies_truncate_guard BEFORE TRUNCATE
    ON public.ingest_file_dependencies FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
