CREATE TABLE public.ucm_snapshot_validations (
    snapshot_id uuid PRIMARY KEY REFERENCES public.ucm_snapshots(id),
    validator_version integer NOT NULL DEFAULT 1 CHECK (validator_version = 1),
    entity_count bigint NOT NULL CHECK (entity_count >= 0),
    validated_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION public.ucm_guard_validation_receipt() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE snapshot_state text;
BEGIN
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
CREATE TRIGGER ucm_validation_receipt_guard BEFORE INSERT OR UPDATE OR DELETE
    ON public.ucm_snapshot_validations FOR EACH ROW
    EXECUTE FUNCTION public.ucm_guard_validation_receipt();
CREATE TRIGGER ucm_validation_receipt_truncate_guard BEFORE TRUNCATE
    ON public.ucm_snapshot_validations FOR EACH STATEMENT
    EXECUTE FUNCTION public.ucm_guard_validation_receipt();

CREATE OR REPLACE FUNCTION public.ucm_guard_snapshot_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'BUILDING' THEN
            RAISE EXCEPTION 'snapshot must start in BUILDING' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
    END IF;
    IF (to_jsonb(NEW) - 'state') IS DISTINCT FROM (to_jsonb(OLD) - 'state') THEN
        RAISE EXCEPTION 'snapshot metadata are immutable' USING ERRCODE='23514';
    END IF;
    IF NEW.state <> OLD.state AND NOT (
        (OLD.state='BUILDING' AND NEW.state='VALIDATING') OR
        (OLD.state='VALIDATING' AND NEW.state='READY') OR
        (OLD.state='READY' AND NEW.state='PUBLISHED') OR
        (OLD.state='PUBLISHED' AND NEW.state='RETIRED') OR
        (OLD.state='RETIRED' AND NEW.state='PUBLISHED')
    ) THEN
        RAISE EXCEPTION 'invalid snapshot state transition' USING ERRCODE='23514';
    END IF;
    IF NEW.state IN ('READY','PUBLISHED') AND NOT EXISTS (
        SELECT 1 FROM public.ucm_snapshot_validations WHERE snapshot_id=NEW.id
    ) THEN
        RAISE EXCEPTION 'snapshot requires validation receipt' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE UNIQUE INDEX ucm_one_published_snapshot_idx ON public.ucm_snapshots(repository_id)
    WHERE state='PUBLISHED';

CREATE FUNCTION public.ucm_check_publication_consistency() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    new_repository uuid;
    old_repository uuid;
    repository uuid;
    selected_snapshot uuid;
    selected_state text;
BEGIN
    IF TG_OP <> 'DELETE' THEN new_repository := NEW.repository_id; END IF;
    IF TG_OP <> 'INSERT' THEN old_repository := OLD.repository_id; END IF;
    FOR repository IN SELECT DISTINCT r FROM unnest(ARRAY[new_repository,old_repository]) r WHERE r IS NOT NULL
    LOOP
        SELECT p.snapshot_id,s.state INTO selected_snapshot,selected_state
            FROM public.ucm_repository_publications p
            JOIN public.ucm_snapshots s ON s.id=p.snapshot_id
            WHERE p.repository_id=repository;
        IF selected_snapshot IS NOT NULL AND selected_state <> 'PUBLISHED' THEN
            RAISE EXCEPTION 'publication pointer requires PUBLISHED snapshot' USING ERRCODE='23514';
        END IF;
        IF EXISTS (SELECT 1 FROM public.ucm_snapshots
            WHERE repository_id=repository AND state='PUBLISHED'
            AND id IS DISTINCT FROM selected_snapshot) THEN
            RAISE EXCEPTION 'PUBLISHED snapshot requires matching publication pointer' USING ERRCODE='23514';
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER ucm_snapshot_publication_consistency
    AFTER INSERT OR UPDATE OR DELETE ON public.ucm_snapshots
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION public.ucm_check_publication_consistency();
CREATE CONSTRAINT TRIGGER ucm_pointer_publication_consistency
    AFTER INSERT OR UPDATE OR DELETE ON public.ucm_repository_publications
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION public.ucm_check_publication_consistency();

CREATE FUNCTION public.ucm_guard_publication_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'publication pointers cannot be truncated' USING ERRCODE='23514';
END;
$$;
CREATE TRIGGER ucm_publication_truncate_guard BEFORE TRUNCATE
    ON public.ucm_repository_publications FOR EACH STATEMENT
    EXECUTE FUNCTION public.ucm_guard_publication_truncate();
