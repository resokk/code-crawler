CREATE TABLE public.ingest_jobs (
    id uuid PRIMARY KEY,
    repository_id uuid NOT NULL REFERENCES public.ucm_repositories(id),
    snapshot_id uuid REFERENCES public.ucm_snapshots(id) ON DELETE SET NULL,
    parameters jsonb NOT NULL,
    state text NOT NULL DEFAULT 'RUNNING' CHECK (state IN ('RUNNING','SUCCEEDED','FAILED')),
    stage text NOT NULL DEFAULT 'INDEX' CHECK (stage IN ('INDEX','PUBLISH')),
    attempt integer NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    failure jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ingest_jobs_repository_idx ON public.ingest_jobs(repository_id, created_at);
CREATE INDEX ingest_jobs_running_idx ON public.ingest_jobs(repository_id) WHERE state='RUNNING';

-- Garbage collection may delete facts of RETIRED snapshots, but only in a transaction
-- that explicitly sets code_crawler.gc; BUILDING facts stay deletable as before.
CREATE OR REPLACE FUNCTION public.ucm_guard_fact_write() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    selected_snapshot uuid;
    snapshot_state text;
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'canonical facts cannot be truncated' USING ERRCODE='23514';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.snapshot_id <> OLD.snapshot_id THEN
        RAISE EXCEPTION 'canonical facts cannot move between snapshots' USING ERRCODE='23514';
    END IF;
    IF TG_OP = 'DELETE' THEN selected_snapshot := OLD.snapshot_id;
    ELSE selected_snapshot := NEW.snapshot_id;
    END IF;
    SELECT state INTO snapshot_state FROM public.ucm_snapshots
        WHERE id=selected_snapshot FOR SHARE;
    IF TG_OP = 'DELETE' AND snapshot_state = 'RETIRED'
        AND current_setting('code_crawler.gc', true) = 'on' THEN
        RETURN OLD;
    END IF;
    IF snapshot_state IS DISTINCT FROM 'BUILDING' THEN
        RAISE EXCEPTION 'canonical facts require BUILDING snapshot' USING ERRCODE='23514';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.ucm_guard_validation_receipt() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE snapshot_state text;
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('code_crawler.gc', true) = 'on' THEN
        SELECT state INTO snapshot_state FROM public.ucm_snapshots
            WHERE id=OLD.snapshot_id FOR SHARE;
        IF snapshot_state = 'RETIRED' THEN RETURN OLD; END IF;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'validation receipts are immutable' USING ERRCODE='23514';
    END IF;
    SELECT state INTO snapshot_state FROM public.ucm_snapshots
        WHERE id=NEW.snapshot_id FOR SHARE;
    IF snapshot_state IS DISTINCT FROM 'VALIDATING' THEN
        RAISE EXCEPTION 'receipt requires VALIDATING snapshot' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
