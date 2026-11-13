CREATE TABLE public.ucm_entities (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL CHECK (entity_id ~ '^ucm:[0-9a-f]{64}$'),
    repository_id uuid NOT NULL,
    contract_version integer NOT NULL DEFAULT 1 CHECK (contract_version = 1),
    entity_type text NOT NULL CHECK (entity_type IN
        ('SOURCE_FILE','CLASS','METHOD','SQL_CANDIDATE','SYMBOL','SCOPE','OCCURRENCE',
         'OPERATION','VALUE','RELATION','EXTERNAL_REFERENCE')),
    logical_key text NOT NULL CHECK (logical_key ~ '\S'),
    name text NOT NULL CHECK (name ~ '\S'),
    source_file_id text,
    start_line integer,
    start_byte_column integer,
    end_line integer,
    end_byte_column integer,
    PRIMARY KEY (snapshot_id, entity_id),
    UNIQUE (snapshot_id, entity_id, entity_type),
    UNIQUE (snapshot_id, entity_type, logical_key),
    FOREIGN KEY (repository_id, snapshot_id) REFERENCES public.ucm_snapshots(repository_id,id),
    CHECK (
        (source_file_id IS NULL AND start_line IS NULL AND start_byte_column IS NULL
         AND end_line IS NULL AND end_byte_column IS NULL) OR
        (source_file_id IS NOT NULL AND start_line IS NOT NULL AND start_byte_column IS NOT NULL
         AND end_line IS NOT NULL AND end_byte_column IS NOT NULL
         AND start_line >= 1 AND start_byte_column >= 0 AND end_line >= 1 AND end_byte_column >= 0
         AND (end_line,end_byte_column) >= (start_line,start_byte_column))
    )
);
CREATE INDEX ucm_entities_snapshot_type_idx ON public.ucm_entities(snapshot_id,entity_type);
CREATE INDEX ucm_entities_source_idx ON public.ucm_entities(snapshot_id,source_file_id);

CREATE TABLE public.ucm_source_files (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'SOURCE_FILE' CHECK (entity_type = 'SOURCE_FILE'),

    path text NOT NULL CHECK (path ~ '\S' AND path !~ '(^/|(^|/)\.\.?(/|$)|//|/$|[:\\])'),
    language text NOT NULL CHECK (language ~ '\S'),
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    UNIQUE (snapshot_id,path),
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,entity_id,entity_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE public.ucm_symbols (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'SYMBOL' CHECK (entity_type = 'SYMBOL'),

    symbol_kind text NOT NULL CHECK (symbol_kind IN ('CLASS','METHOD','CONSTRUCTOR','FIELD','PARAMETER','LOCAL_VARIABLE')),
    qualified_name text NOT NULL CHECK (qualified_name ~ '\S'),
    scope_id text,
    owner_key text CHECK (owner_key IS NULL OR owner_key ~ '\S'),
    CHECK ((symbol_kind IN ('METHOD','CONSTRUCTOR')) = (owner_key IS NOT NULL)),
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,entity_id,entity_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE public.ucm_scopes (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'SCOPE' CHECK (entity_type = 'SCOPE'),

    scope_kind text NOT NULL CHECK (scope_kind IN ('FILE','TYPE','CALLABLE','BLOCK')),
    parent_scope_id text,
    owner_symbol_id text,
    FOREIGN KEY (snapshot_id,parent_scope_id) REFERENCES public.ucm_scopes(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (snapshot_id,owner_symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,entity_id,entity_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE public.ucm_occurrences (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'OCCURRENCE' CHECK (entity_type = 'OCCURRENCE'),

    occurrence_kind text NOT NULL CHECK (occurrence_kind IN ('DECLARATION','REFERENCE','READ','WRITE','CALL')),
    scope_id text NOT NULL,
    resolution text NOT NULL CHECK (resolution IN ('UNRESOLVED','RESOLVED','AMBIGUOUS')),
    target_symbol_id text,
    CHECK ((resolution = 'RESOLVED') = (target_symbol_id IS NOT NULL)),
    FOREIGN KEY (snapshot_id,scope_id) REFERENCES public.ucm_scopes(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (snapshot_id,target_symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,entity_id,entity_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE public.ucm_values (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'VALUE' CHECK (entity_type = 'VALUE'),

    value_kind text NOT NULL CHECK (value_kind IN ('LITERAL','SYMBOLIC','UNKNOWN')),
    partial boolean NOT NULL,
    literal jsonb,
    CHECK (literal IS NULL OR jsonb_typeof(literal) IN ('null','string','number','boolean')),
    CHECK (value_kind = 'LITERAL' OR literal IS NULL),
    CHECK (value_kind <> 'LITERAL' OR NOT partial),
    CHECK (value_kind <> 'UNKNOWN' OR partial),
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,entity_id,entity_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE public.ucm_operations (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'OPERATION' CHECK (entity_type = 'OPERATION'),

    operation_kind text NOT NULL CHECK (operation_kind IN ('READ','ASSIGN','CALL','RETURN','CONCAT')),
    scope_id text NOT NULL,
    FOREIGN KEY (snapshot_id,scope_id) REFERENCES public.ucm_scopes(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,entity_id,entity_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type)
        DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE public.ucm_entities ADD FOREIGN KEY (snapshot_id,source_file_id)
    REFERENCES public.ucm_source_files(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE public.ucm_symbols ADD FOREIGN KEY (snapshot_id,scope_id)
    REFERENCES public.ucm_scopes(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX ucm_symbols_name_idx ON public.ucm_symbols(snapshot_id,qualified_name);
CREATE TABLE public.ucm_operation_values (
    snapshot_id uuid NOT NULL,
    operation_id text NOT NULL,
    direction text NOT NULL CHECK (direction IN ('INPUT','OUTPUT')),
    position integer NOT NULL CHECK (position >= 0),
    value_id text NOT NULL,
    PRIMARY KEY (snapshot_id,operation_id,direction,position),
    FOREIGN KEY (snapshot_id,operation_id) REFERENCES public.ucm_operations(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (snapshot_id,value_id) REFERENCES public.ucm_values(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE UNIQUE INDEX ucm_operation_unique_output_idx ON public.ucm_operation_values(snapshot_id,operation_id,value_id) WHERE direction='OUTPUT';
CREATE INDEX ucm_operation_values_reverse_idx ON public.ucm_operation_values(snapshot_id,value_id);
CREATE TABLE public.ucm_type_refs (
    snapshot_id uuid NOT NULL,
    owner_id text NOT NULL,
    role text NOT NULL CHECK (role IN ('TYPE','PARAMETER','RETURN','CALLEE')),
    position integer NOT NULL CHECK (position >= 0 AND (role='PARAMETER' OR position=0)),
    name text NOT NULL CHECK (name ~ '\S'),
    resolution text NOT NULL CHECK (resolution IN ('UNRESOLVED','RESOLVED','AMBIGUOUS')),
    target_symbol_id text,
    PRIMARY KEY (snapshot_id,owner_id,role,position),
    CHECK ((resolution='RESOLVED') = (target_symbol_id IS NOT NULL)),
    FOREIGN KEY (snapshot_id,owner_id) REFERENCES public.ucm_entities(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (snapshot_id,target_symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_relation_sources (
    relation_kind text NOT NULL,
    source_type text NOT NULL,
    PRIMARY KEY (relation_kind,source_type)
);
CREATE TABLE public.ucm_relation_endpoints (
    relation_kind text NOT NULL,
    source_type text NOT NULL,
    target_type text NOT NULL,
    PRIMARY KEY (relation_kind,source_type,target_type),
    FOREIGN KEY (relation_kind,source_type) REFERENCES public.ucm_relation_sources(relation_kind,source_type)
);
INSERT INTO public.ucm_relation_sources VALUES
('CALLS', 'METHOD'),
('CALLS', 'OPERATION'),
('CALLS', 'SYMBOL'),
('CONSUMES', 'OPERATION'),
('CONTAINS', 'CLASS'),
('CONTAINS', 'SCOPE'),
('CONTAINS', 'SOURCE_FILE'),
('CONTAINS', 'SYMBOL'),
('DECLARES', 'OCCURRENCE'),
('EXTERNAL_DEPENDENCY', 'METHOD'),
('EXTERNAL_DEPENDENCY', 'OCCURRENCE'),
('EXTERNAL_DEPENDENCY', 'OPERATION'),
('EXTERNAL_DEPENDENCY', 'SYMBOL'),
('EXTERNAL_DEPENDENCY', 'VALUE'),
('FLOWS_TO', 'VALUE'),
('PRODUCES', 'OPERATION'),
('REFERENCES', 'OCCURRENCE');
INSERT INTO public.ucm_relation_endpoints VALUES
('CALLS', 'METHOD', 'METHOD'),
('CALLS', 'METHOD', 'SYMBOL'),
('CALLS', 'OPERATION', 'METHOD'),
('CALLS', 'OPERATION', 'SYMBOL'),
('CALLS', 'SYMBOL', 'METHOD'),
('CALLS', 'SYMBOL', 'SYMBOL'),
('CONSUMES', 'OPERATION', 'VALUE'),
('CONTAINS', 'CLASS', 'CLASS'),
('CONTAINS', 'CLASS', 'METHOD'),
('CONTAINS', 'CLASS', 'OPERATION'),
('CONTAINS', 'CLASS', 'SCOPE'),
('CONTAINS', 'CLASS', 'SYMBOL'),
('CONTAINS', 'SCOPE', 'CLASS'),
('CONTAINS', 'SCOPE', 'METHOD'),
('CONTAINS', 'SCOPE', 'OPERATION'),
('CONTAINS', 'SCOPE', 'SCOPE'),
('CONTAINS', 'SCOPE', 'SYMBOL'),
('CONTAINS', 'SOURCE_FILE', 'CLASS'),
('CONTAINS', 'SOURCE_FILE', 'METHOD'),
('CONTAINS', 'SOURCE_FILE', 'OPERATION'),
('CONTAINS', 'SOURCE_FILE', 'SCOPE'),
('CONTAINS', 'SOURCE_FILE', 'SYMBOL'),
('CONTAINS', 'SYMBOL', 'CLASS'),
('CONTAINS', 'SYMBOL', 'METHOD'),
('CONTAINS', 'SYMBOL', 'OPERATION'),
('CONTAINS', 'SYMBOL', 'SCOPE'),
('CONTAINS', 'SYMBOL', 'SYMBOL'),
('DECLARES', 'OCCURRENCE', 'CLASS'),
('DECLARES', 'OCCURRENCE', 'METHOD'),
('DECLARES', 'OCCURRENCE', 'SYMBOL'),
('EXTERNAL_DEPENDENCY', 'METHOD', 'EXTERNAL_REFERENCE'),
('EXTERNAL_DEPENDENCY', 'OCCURRENCE', 'EXTERNAL_REFERENCE'),
('EXTERNAL_DEPENDENCY', 'OPERATION', 'EXTERNAL_REFERENCE'),
('EXTERNAL_DEPENDENCY', 'SYMBOL', 'EXTERNAL_REFERENCE'),
('EXTERNAL_DEPENDENCY', 'VALUE', 'EXTERNAL_REFERENCE'),
('FLOWS_TO', 'VALUE', 'VALUE'),
('PRODUCES', 'OPERATION', 'VALUE'),
('REFERENCES', 'OCCURRENCE', 'CLASS'),
('REFERENCES', 'OCCURRENCE', 'METHOD'),
('REFERENCES', 'OCCURRENCE', 'SYMBOL');

CREATE TABLE public.ucm_relations (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'RELATION' CHECK (entity_type = 'RELATION'),

    relation_kind text NOT NULL,
    source_id text NOT NULL,
    source_type text NOT NULL,
    target_id text,
    target_type text,
    resolution text NOT NULL CHECK (resolution IN ('RESOLVED','UNRESOLVED','AMBIGUOUS','PARTIAL')),
    reason text CHECK (reason IS NULL OR reason ~ '\S'),
    UNIQUE (snapshot_id,entity_id,relation_kind,source_type),
    CHECK ((target_id IS NULL) = (target_type IS NULL)),
    CHECK ((resolution='RESOLVED') = (target_id IS NOT NULL)),
    CHECK (resolution='RESOLVED' OR reason IS NOT NULL),
    FOREIGN KEY (relation_kind,source_type) REFERENCES public.ucm_relation_sources(relation_kind,source_type),
    FOREIGN KEY (relation_kind,source_type,target_type) REFERENCES public.ucm_relation_endpoints(relation_kind,source_type,target_type),
    FOREIGN KEY (snapshot_id,source_id,source_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (snapshot_id,target_id,target_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,

    certainty text NOT NULL CHECK (certainty IN ('STATIC_PROVEN','INFERRED','UNKNOWN')),
    coverage_capability text NOT NULL CHECK (coverage_capability ~ '\S'),
    coverage_analyzer_version text NOT NULL CHECK (coverage_analyzer_version ~ '\S'),
    coverage_status text NOT NULL CHECK (coverage_status IN ('COMPLETE','PARTIAL','UNSUPPORTED')),
    CHECK (certainty <> 'STATIC_PROVEN' OR resolution='RESOLVED'),
    CHECK (coverage_status <> 'UNSUPPORTED' OR (resolution='UNRESOLVED' AND certainty='UNKNOWN')),
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,entity_id,entity_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX ucm_relations_source_idx ON public.ucm_relations(snapshot_id,source_id,relation_kind);
CREATE INDEX ucm_relations_target_idx ON public.ucm_relations(snapshot_id,target_id,relation_kind);
CREATE TABLE public.ucm_relation_candidates (
    snapshot_id uuid NOT NULL,
    relation_id text NOT NULL,
    relation_kind text NOT NULL,
    source_type text NOT NULL,
    candidate_id text NOT NULL,
    candidate_type text NOT NULL,
    PRIMARY KEY (snapshot_id,relation_id,candidate_id),
    FOREIGN KEY (snapshot_id,relation_id,relation_kind,source_type)
        REFERENCES public.ucm_relations(snapshot_id,entity_id,relation_kind,source_type) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (relation_kind,source_type,candidate_type)
        REFERENCES public.ucm_relation_endpoints(relation_kind,source_type,target_type),
    FOREIGN KEY (snapshot_id,candidate_id,candidate_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE public.ucm_external_references (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'EXTERNAL_REFERENCE' CHECK (entity_type = 'EXTERNAL_REFERENCE'),

    source_id text NOT NULL,
    source_type text NOT NULL CHECK (source_type IN ('SYMBOL','METHOD','OCCURRENCE','OPERATION','VALUE')),
    selector_kind text NOT NULL CHECK (selector_kind IN ('SYMBOL','HTTP','DATABASE')),
    qualified_name text CHECK (qualified_name IS NULL OR qualified_name ~ '\S'),
    parameter_type_names text[],
    http_method text CHECK (http_method IN ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT')),
    http_path text CHECK (http_path LIKE '/%' AND http_path !~ '[?#]'),
    service text CHECK (service IS NULL OR service ~ '\S'),
    connection text CHECK (connection IS NULL OR connection ~ '\S'),
    schema_name text CHECK (schema_name IS NULL OR schema_name ~ '\S'),
    table_name text CHECK (table_name IS NULL OR table_name ~ '\S'),
    repository_hint text CHECK (repository_hint IS NULL OR repository_hint ~ '\S'),
    version_hint text CHECK (version_hint IS NULL OR version_hint ~ '\S'),
    resolution text NOT NULL DEFAULT 'UNRESOLVED' CHECK (resolution='UNRESOLVED'),
    reason text NOT NULL CHECK (reason ~ '\S'),
    FOREIGN KEY (snapshot_id,source_id,source_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,

    certainty text NOT NULL CHECK (certainty IN ('STATIC_PROVEN','INFERRED','UNKNOWN')),
    coverage_capability text NOT NULL CHECK (coverage_capability ~ '\S'),
    coverage_analyzer_version text NOT NULL CHECK (coverage_analyzer_version ~ '\S'),
    coverage_status text NOT NULL CHECK (coverage_status IN ('COMPLETE','PARTIAL','UNSUPPORTED')),
    CHECK (coverage_status <> 'UNSUPPORTED' OR certainty='UNKNOWN'),
    CHECK (
        (selector_kind='SYMBOL' AND qualified_name IS NOT NULL
         AND http_method IS NULL AND http_path IS NULL AND service IS NULL
         AND connection IS NULL AND schema_name IS NULL AND table_name IS NULL) OR
        (selector_kind='HTTP' AND http_method IS NOT NULL AND http_path IS NOT NULL
         AND qualified_name IS NULL AND parameter_type_names IS NULL
         AND connection IS NULL AND schema_name IS NULL AND table_name IS NULL) OR
        (selector_kind='DATABASE' AND connection IS NOT NULL AND table_name IS NOT NULL
         AND qualified_name IS NULL AND parameter_type_names IS NULL
         AND http_method IS NULL AND http_path IS NULL AND service IS NULL)
    ),
    PRIMARY KEY (snapshot_id,entity_id),
    FOREIGN KEY (snapshot_id,entity_id,entity_type)
        REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE public.ucm_evidence (
    snapshot_id uuid NOT NULL,
    owner_id text NOT NULL,
    owner_type text NOT NULL CHECK (owner_type IN ('RELATION','EXTERNAL_REFERENCE')),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    source_file_id text NOT NULL,
    start_line integer NOT NULL CHECK (start_line >= 1),
    start_byte_column integer NOT NULL CHECK (start_byte_column >= 0),
    end_line integer NOT NULL CHECK (end_line >= 1),
    end_byte_column integer NOT NULL CHECK (end_byte_column >= 0),
    analyzer text NOT NULL CHECK (analyzer ~ '\S'),
    analyzer_version text NOT NULL CHECK (analyzer_version ~ '\S'),
    rule text NOT NULL CHECK (rule ~ '\S'),
    description text NOT NULL CHECK (description ~ '\S'),
    PRIMARY KEY (snapshot_id,owner_id,ordinal),
    CHECK ((end_line,end_byte_column) >= (start_line,start_byte_column)),
    FOREIGN KEY (snapshot_id,owner_id,owner_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (snapshot_id,source_file_id) REFERENCES public.ucm_source_files(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_coverage_reasons (
    snapshot_id uuid NOT NULL,
    owner_id text NOT NULL,
    owner_type text NOT NULL CHECK (owner_type IN ('RELATION','EXTERNAL_REFERENCE')),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    reason text NOT NULL CHECK (reason ~ '\S'),
    PRIMARY KEY (snapshot_id,owner_id,ordinal),
    FOREIGN KEY (snapshot_id,owner_id,owner_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED
);
CREATE FUNCTION public.ucm_guard_fact_write() RETURNS trigger
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
    IF snapshot_state IS DISTINCT FROM 'BUILDING' THEN
        RAISE EXCEPTION 'canonical facts require BUILDING snapshot' USING ERRCODE='23514';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ucm_entities_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_entities
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_entities_truncate_guard BEFORE TRUNCATE ON public.ucm_entities
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_files_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_source_files
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_files_truncate_guard BEFORE TRUNCATE ON public.ucm_source_files
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_symbols_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_symbols
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_symbols_truncate_guard BEFORE TRUNCATE ON public.ucm_symbols
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_scopes_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_scopes
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_scopes_truncate_guard BEFORE TRUNCATE ON public.ucm_scopes
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_occurrences_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_occurrences
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_occurrences_truncate_guard BEFORE TRUNCATE ON public.ucm_occurrences
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_operations_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_operations
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_operations_truncate_guard BEFORE TRUNCATE ON public.ucm_operations
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_values_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_values
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_values_truncate_guard BEFORE TRUNCATE ON public.ucm_values
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_operation_values_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_operation_values
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_operation_values_truncate_guard BEFORE TRUNCATE ON public.ucm_operation_values
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_type_refs_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_type_refs
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_type_refs_truncate_guard BEFORE TRUNCATE ON public.ucm_type_refs
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_relations_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_relations
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_relations_truncate_guard BEFORE TRUNCATE ON public.ucm_relations
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_relation_candidates_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_relation_candidates
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_relation_candidates_truncate_guard BEFORE TRUNCATE ON public.ucm_relation_candidates
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_external_references_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_external_references
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_external_references_truncate_guard BEFORE TRUNCATE ON public.ucm_external_references
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_evidence_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_evidence
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_evidence_truncate_guard BEFORE TRUNCATE ON public.ucm_evidence
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_coverage_reasons_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_coverage_reasons
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_coverage_reasons_truncate_guard BEFORE TRUNCATE ON public.ucm_coverage_reasons
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
