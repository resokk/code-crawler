CREATE TABLE public.ingest_snapshot_adapters (
    snapshot_id uuid NOT NULL REFERENCES public.ucm_snapshots(id),
    adapter_key text NOT NULL CHECK (adapter_key ~ '\S'),
    analysis_version text NOT NULL CHECK (analysis_version ~ '\S'),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (snapshot_id,adapter_key)
);
CREATE TRIGGER ingest_snapshot_adapters_write_guard BEFORE INSERT OR UPDATE OR DELETE
    ON public.ingest_snapshot_adapters FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ingest_snapshot_adapters_truncate_guard BEFORE TRUNCATE
    ON public.ingest_snapshot_adapters FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
