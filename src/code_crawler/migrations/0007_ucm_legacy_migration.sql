CREATE TABLE public.ucm_legacy_repositories (
    repository_id uuid PRIMARY KEY REFERENCES public.ucm_repositories(id),
    legacy_repo_id bigint NOT NULL UNIQUE REFERENCES public.repos(id),
    read_backend text NOT NULL DEFAULT 'legacy' CHECK (read_backend IN ('legacy','ucm'))
);
CREATE TABLE public.ingest_legacy_nodes (
    snapshot_id uuid NOT NULL REFERENCES public.ucm_snapshots(id),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    entity_id text NOT NULL,
    kind text NOT NULL,
    name text NOT NULL,
    qualified_name text NOT NULL,
    file_path text,
    start_line integer,
    end_line integer,
    attrs jsonb NOT NULL,
    PRIMARY KEY(snapshot_id,ordinal),
    FOREIGN KEY(snapshot_id,entity_id) REFERENCES public.ucm_entities(snapshot_id,entity_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ingest_legacy_edges (
    snapshot_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    src integer NOT NULL,
    dst integer NOT NULL,
    kind text NOT NULL,
    attrs jsonb NOT NULL,
    PRIMARY KEY(snapshot_id,ordinal),
    FOREIGN KEY(snapshot_id,src) REFERENCES public.ingest_legacy_nodes(snapshot_id,ordinal) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(snapshot_id,dst) REFERENCES public.ingest_legacy_nodes(snapshot_id,ordinal) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ingest_legacy_refs (
    snapshot_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    node integer NOT NULL,
    kind text NOT NULL,
    table_name text NOT NULL,
    column_name text,
    attrs jsonb NOT NULL,
    PRIMARY KEY(snapshot_id,ordinal),
    FOREIGN KEY(snapshot_id,node) REFERENCES public.ingest_legacy_nodes(snapshot_id,ordinal) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ingest_legacy_snapshots (
    snapshot_id uuid PRIMARY KEY REFERENCES public.ucm_snapshots(id),
    legacy_repo_id bigint NOT NULL REFERENCES public.repos(id),
    node_count integer NOT NULL CHECK(node_count>=0),
    edge_count integer NOT NULL CHECK(edge_count>=0),
    ref_count integer NOT NULL CHECK(ref_count>=0)
);
CREATE TRIGGER ingest_legacy_nodes_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ingest_legacy_nodes
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_legacy_nodes_truncate_guard BEFORE TRUNCATE ON public.ingest_legacy_nodes
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_legacy_edges_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ingest_legacy_edges
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_legacy_edges_truncate_guard BEFORE TRUNCATE ON public.ingest_legacy_edges
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_legacy_refs_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ingest_legacy_refs
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_legacy_refs_truncate_guard BEFORE TRUNCATE ON public.ingest_legacy_refs
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_legacy_snapshots_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ingest_legacy_snapshots
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_legacy_snapshots_truncate_guard BEFORE TRUNCATE ON public.ingest_legacy_snapshots
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
