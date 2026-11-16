CREATE TABLE search_index_generations (
    id uuid PRIMARY KEY,
    repository_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    projection_version text NOT NULL CHECK (projection_version ~ '\S'),
    policy_version text NOT NULL CHECK (policy_version ~ '\S'),
    document_count bigint NOT NULL CHECK (document_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (repository_id, snapshot_id, id),
    FOREIGN KEY (repository_id, snapshot_id)
        REFERENCES ucm_snapshots(repository_id, id) ON DELETE CASCADE
);

CREATE TABLE search_documents (
    repository_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    generation_id uuid NOT NULL,
    document_id text NOT NULL,
    entity_id text NOT NULL,
    document_type text NOT NULL CHECK (document_type IN
        ('SYMBOL', 'SQL_STATEMENT', 'DATABASE_OBJECT', 'CALL_SUMMARY', 'ORM_MAPPING', 'ORM_QUERY')),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    provenance jsonb NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
    PRIMARY KEY (generation_id, document_id),
    FOREIGN KEY (repository_id, snapshot_id, generation_id)
        REFERENCES search_index_generations(repository_id, snapshot_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id, entity_id)
        REFERENCES ucm_entities(snapshot_id, entity_id) ON DELETE CASCADE
);

CREATE TABLE search_index_publications (
    repository_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    generation_id uuid NOT NULL,
    PRIMARY KEY (repository_id, snapshot_id),
    FOREIGN KEY (repository_id, snapshot_id, generation_id)
        REFERENCES search_index_generations(repository_id, snapshot_id, id)
        ON DELETE CASCADE
);

ALTER TABLE search_index_generations ADD COLUMN sealed boolean NOT NULL DEFAULT false;

CREATE FUNCTION search_guard_generation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.sealed THEN
            RAISE EXCEPTION 'generation must start unsealed' USING ERRCODE='23514';
        END IF;
    ELSE
        IF OLD.sealed OR (to_jsonb(NEW)-'sealed') IS DISTINCT FROM (to_jsonb(OLD)-'sealed') THEN
            RAISE EXCEPTION 'generation metadata are immutable' USING ERRCODE='23514';
        END IF;
        IF NEW.sealed AND NEW.document_count <> (
            SELECT count(*) FROM search_documents WHERE generation_id=NEW.id
        ) THEN
            RAISE EXCEPTION 'incomplete search generation' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER search_generation_guard BEFORE INSERT OR UPDATE ON search_index_generations
    FOR EACH ROW EXECUTE FUNCTION search_guard_generation();

CREATE FUNCTION search_guard_document() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE target uuid; is_sealed boolean;
BEGIN
    IF TG_OP = 'DELETE' THEN target := OLD.generation_id;
    ELSE target := NEW.generation_id;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'search documents are immutable' USING ERRCODE='23514';
    END IF;
    SELECT sealed INTO is_sealed FROM search_index_generations WHERE id=target FOR SHARE;
    IF is_sealed THEN
        RAISE EXCEPTION 'sealed search generation is immutable' USING ERRCODE='23514';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER search_document_guard BEFORE INSERT OR UPDATE OR DELETE ON search_documents
    FOR EACH ROW EXECUTE FUNCTION search_guard_document();

CREATE FUNCTION search_guard_publication() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM search_index_generations
        WHERE id=NEW.generation_id AND sealed
    ) THEN
        RAISE EXCEPTION 'publication requires sealed search generation' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER search_publication_guard BEFORE INSERT OR UPDATE ON search_index_publications
    FOR EACH ROW EXECUTE FUNCTION search_guard_publication();

CREATE TRIGGER search_documents_truncate_guard BEFORE TRUNCATE ON search_documents
    FOR EACH STATEMENT EXECUTE FUNCTION ucm_guard_publication_truncate();
CREATE TRIGGER search_generations_truncate_guard BEFORE TRUNCATE ON search_index_generations
    FOR EACH STATEMENT EXECUTE FUNCTION ucm_guard_publication_truncate();
CREATE TRIGGER search_publications_truncate_guard BEFORE TRUNCATE ON search_index_publications
    FOR EACH STATEMENT EXECUTE FUNCTION ucm_guard_publication_truncate();
