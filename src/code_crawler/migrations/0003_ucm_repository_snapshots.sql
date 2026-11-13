CREATE TABLE public.ucm_repositories (
    id uuid PRIMARY KEY,
    repository_key text NOT NULL UNIQUE CHECK (repository_key ~ '\S'),
    display_name text NOT NULL CHECK (display_name ~ '\S'),
    source text NOT NULL CHECK (source ~ '\S'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.ucm_snapshots (
    id uuid PRIMARY KEY,
    repository_id uuid NOT NULL REFERENCES public.ucm_repositories(id),
    commit_hash text NOT NULL CHECK (commit_hash ~ '\S'),
    branch text CHECK (branch IS NULL OR branch ~ '\S'),
    source_fingerprint text NOT NULL CHECK (source_fingerprint ~ '^[0-9a-f]{64}$'),
    dirty boolean NOT NULL,
    state text NOT NULL DEFAULT 'BUILDING'
        CHECK (state IN ('BUILDING', 'VALIDATING', 'READY', 'PUBLISHED', 'RETIRED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (repository_id, id)
);
CREATE INDEX ucm_snapshots_repository_created_idx
    ON public.ucm_snapshots(repository_id, created_at, id);

CREATE TABLE public.ucm_repository_publications (
    repository_id uuid PRIMARY KEY REFERENCES public.ucm_repositories(id),
    snapshot_id uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (repository_id, snapshot_id)
        REFERENCES public.ucm_snapshots(repository_id, id)
);

CREATE FUNCTION public.ucm_guard_snapshot_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'BUILDING' THEN
            RAISE EXCEPTION 'snapshot must start in BUILDING' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF (to_jsonb(NEW) - 'state') IS DISTINCT FROM (to_jsonb(OLD) - 'state') THEN
        RAISE EXCEPTION 'snapshot metadata are immutable' USING ERRCODE = '23514';
    END IF;
    IF NEW.state <> OLD.state AND NOT (
        (OLD.state = 'BUILDING' AND NEW.state = 'VALIDATING') OR
        (OLD.state = 'VALIDATING' AND NEW.state = 'READY') OR
        (OLD.state = 'READY' AND NEW.state = 'PUBLISHED') OR
        (OLD.state = 'PUBLISHED' AND NEW.state = 'RETIRED')
    ) THEN
        RAISE EXCEPTION 'invalid snapshot state transition' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ucm_snapshot_update_guard BEFORE INSERT OR UPDATE ON public.ucm_snapshots
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_snapshot_update();
