CREATE TABLE public.resolver_cache_entries (
    cache_key text PRIMARY KEY CHECK(cache_key ~ '^[0-9a-f]{64}$'),
    source_repository_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    reference_id text NOT NULL,
    selector_hash text NOT NULL CHECK(selector_hash ~ '^[0-9a-f]{64}$'),
    context_fingerprint text NOT NULL CHECK(context_fingerprint ~ '^[0-9a-f]{64}$'),
    generations_hash text NOT NULL CHECK(generations_hash ~ '^[0-9a-f]{64}$'),
    algorithm_version text NOT NULL,
    discovery_version text NOT NULL,
    candidate_limit integer NOT NULL CHECK(candidate_limit BETWEEN 1 AND 200),
    payload text NOT NULL CHECK(octet_length(payload) <= 262144),
    payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK(expires_at > created_at AND expires_at <= created_at + interval '1 hour'),
    FOREIGN KEY(source_repository_id,snapshot_id)
        REFERENCES public.ucm_snapshots(repository_id,id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_id,reference_id)
        REFERENCES public.ucm_external_references(snapshot_id,entity_id) ON DELETE CASCADE
);
CREATE INDEX resolver_cache_source_idx ON public.resolver_cache_entries(snapshot_id,reference_id);
CREATE INDEX resolver_cache_expiry_idx ON public.resolver_cache_entries(expires_at);
CREATE INDEX resolver_cache_age_idx ON public.resolver_cache_entries(created_at,cache_key);
CREATE TABLE public.resolver_cache_dependencies (
    cache_key text NOT NULL REFERENCES public.resolver_cache_entries(cache_key) ON DELETE CASCADE,
    repository_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    generation uuid NOT NULL,
    FOREIGN KEY(snapshot_id,generation)
        REFERENCES public.search_discovery_generations(snapshot_id,generation) ON DELETE CASCADE,
    PRIMARY KEY(cache_key,repository_id),
    FOREIGN KEY(repository_id,snapshot_id)
        REFERENCES public.ucm_snapshots(repository_id,id) ON DELETE CASCADE
);
CREATE INDEX resolver_cache_dependency_snapshot_idx ON public.resolver_cache_dependencies(snapshot_id,generation);
CREATE FUNCTION public.resolver_cache_dependency_deleted() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM public.resolver_cache_entries WHERE cache_key=OLD.cache_key;
    RETURN OLD;
END $$;
CREATE TRIGGER resolver_cache_dependency_cleanup AFTER DELETE ON public.resolver_cache_dependencies
    FOR EACH ROW EXECUTE FUNCTION public.resolver_cache_dependency_deleted();
