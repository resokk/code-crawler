ALTER TABLE public.ucm_entities DROP CONSTRAINT ucm_entities_entity_type_check;
ALTER TABLE public.ucm_entities ADD CHECK (entity_type IN
    ('SOURCE_FILE','CLASS','METHOD','SQL_CANDIDATE','SYMBOL','SCOPE','OCCURRENCE',
     'OPERATION','VALUE','RELATION','EXTERNAL_REFERENCE','SQL_CONSTRUCTION'));
INSERT INTO public.ucm_relation_sources VALUES ('CONSTRUCTS_SQL','SYMBOL'),('HAS_SQL_CANDIDATE','SQL_CONSTRUCTION');
INSERT INTO public.ucm_relation_endpoints VALUES ('CONSTRUCTS_SQL','SYMBOL','SQL_CONSTRUCTION'),('HAS_SQL_CANDIDATE','SQL_CONSTRUCTION','SQL_CANDIDATE');
CREATE TABLE public.ucm_sql_constructions (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'SQL_CONSTRUCTION' CHECK(entity_type='SQL_CONSTRUCTION'),
    owner_symbol_id text NOT NULL,
    PRIMARY KEY(snapshot_id,entity_id),
    FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(snapshot_id,owner_symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_sql_variants (
    snapshot_id uuid NOT NULL,
    candidate_id text NOT NULL,
    candidate_type text NOT NULL DEFAULT 'SQL_CANDIDATE' CHECK(candidate_type='SQL_CANDIDATE'),
    construction_id text NOT NULL,
    position integer NOT NULL CHECK(position>=0),
    text text NOT NULL CHECK(text ~ '\S'),
    partial boolean NOT NULL,
    PRIMARY KEY(snapshot_id,candidate_id),
    UNIQUE(snapshot_id,construction_id,position),
    FOREIGN KEY(snapshot_id,candidate_id,candidate_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(snapshot_id,construction_id) REFERENCES public.ucm_sql_constructions(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_sql_fragments (
    snapshot_id uuid NOT NULL,
    candidate_id text NOT NULL,
    ordinal integer NOT NULL CHECK(ordinal>=0),
    kind text NOT NULL CHECK(kind IN ('STATIC','DYNAMIC')),
    text text NOT NULL,
    source_file_id text,
    start_line integer,
    start_byte_column integer,
    end_line integer,
    end_byte_column integer,
    PRIMARY KEY(snapshot_id,candidate_id,ordinal),
    FOREIGN KEY(snapshot_id,candidate_id) REFERENCES public.ucm_sql_variants(snapshot_id,candidate_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(snapshot_id,source_file_id) REFERENCES public.ucm_source_files(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK ((source_file_id IS NULL AND start_line IS NULL AND start_byte_column IS NULL AND end_line IS NULL AND end_byte_column IS NULL) OR
           (source_file_id IS NOT NULL AND start_line IS NOT NULL AND start_byte_column IS NOT NULL AND end_line IS NOT NULL AND end_byte_column IS NOT NULL
            AND start_line>=1 AND start_byte_column>=0 AND end_line>=1 AND end_byte_column>=0
            AND (end_line,end_byte_column)>=(start_line,start_byte_column)))
);
CREATE TABLE public.ucm_sql_partial_reasons (
    snapshot_id uuid NOT NULL,
    candidate_id text NOT NULL,
    ordinal integer NOT NULL CHECK(ordinal>=0),
    reason text NOT NULL CHECK(reason ~ '\S'),
    PRIMARY KEY(snapshot_id,candidate_id,ordinal),
    FOREIGN KEY(snapshot_id,candidate_id) REFERENCES public.ucm_sql_variants(snapshot_id,candidate_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER ucm_sql_constructions_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_constructions
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_constructions_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_constructions
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_variants_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_variants
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_variants_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_variants
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_fragments_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_fragments
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_fragments_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_fragments
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_partial_reasons_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_partial_reasons
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_partial_reasons_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_partial_reasons
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
