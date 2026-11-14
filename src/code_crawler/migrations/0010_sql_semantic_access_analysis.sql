ALTER TABLE public.ucm_entities DROP CONSTRAINT ucm_entities_entity_type_check;
ALTER TABLE public.ucm_entities ADD CHECK (entity_type IN
    ('SOURCE_FILE','CLASS','METHOD','SQL_CANDIDATE','SYMBOL','SCOPE','OCCURRENCE',
     'OPERATION','VALUE','RELATION','EXTERNAL_REFERENCE','SQL_CONSTRUCTION','SQL_EXECUTE',
     'SQL_STATEMENT','DATA_ACCESS'));
INSERT INTO public.ucm_relation_sources VALUES
 ('HAS_SQL_STATEMENT','SQL_CANDIDATE'),('EXECUTES_STATEMENT','SQL_EXECUTE'),
 ('READS_FROM','SQL_STATEMENT'),('INSERTS_INTO','SQL_STATEMENT'),('UPDATES','SQL_STATEMENT'),
 ('DELETES_FROM','SQL_STATEMENT'),('MERGES_INTO','SQL_STATEMENT'),('DDL_ON','SQL_STATEMENT');
INSERT INTO public.ucm_relation_endpoints VALUES
 ('HAS_SQL_STATEMENT','SQL_CANDIDATE','SQL_STATEMENT'),('EXECUTES_STATEMENT','SQL_EXECUTE','SQL_STATEMENT'),
 ('READS_FROM','SQL_STATEMENT','DATA_ACCESS'),('INSERTS_INTO','SQL_STATEMENT','DATA_ACCESS'),
 ('UPDATES','SQL_STATEMENT','DATA_ACCESS'),('DELETES_FROM','SQL_STATEMENT','DATA_ACCESS'),
 ('MERGES_INTO','SQL_STATEMENT','DATA_ACCESS'),('DDL_ON','SQL_STATEMENT','DATA_ACCESS');
CREATE TABLE public.ucm_sql_statements (
 snapshot_id uuid NOT NULL, entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'SQL_STATEMENT' CHECK(entity_type='SQL_STATEMENT'),
 candidate_id text NOT NULL, statement_index integer NOT NULL CHECK(statement_index>=0),
 dialect text NOT NULL CHECK(dialect IN ('postgres','mysql','tsql')),
 text text NOT NULL CHECK(text ~ '\S'), text_start integer NOT NULL CHECK(text_start>=0),
 text_end integer NOT NULL CHECK(text_end>text_start),
 operation text NOT NULL CHECK(operation IN ('SELECT','INSERT','UPDATE','DELETE','MERGE','DDL','UNKNOWN')),
 parse_status text NOT NULL CHECK(parse_status IN ('COMPLETE','PARTIAL','ERROR','UNSUPPORTED')),
 PRIMARY KEY(snapshot_id,entity_id), UNIQUE(snapshot_id,candidate_id,statement_index),
 CHECK(text_end-text_start=char_length(text)),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,candidate_id) REFERENCES public.ucm_sql_variants(snapshot_id,candidate_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_sql_statement_reasons (
 snapshot_id uuid NOT NULL, statement_id text NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=0),
 reason text NOT NULL CHECK(reason ~ '\S'), PRIMARY KEY(snapshot_id,statement_id,ordinal),
 FOREIGN KEY(snapshot_id,statement_id) REFERENCES public.ucm_sql_statements(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_data_accesses (
 snapshot_id uuid NOT NULL, entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'DATA_ACCESS' CHECK(entity_type='DATA_ACCESS'),
 statement_id text NOT NULL,
 object_kind text NOT NULL CHECK(object_kind IN ('TABLE','COLUMN')),
 access_kind text NOT NULL CHECK(access_kind IN ('READ','INSERT','UPDATE','DELETE','MERGE','DDL')),
 role text NOT NULL CHECK(role ~ '\S'),
 binding_status text NOT NULL CHECK(binding_status IN ('BOUND','UNBOUND','AMBIGUOUS')),
 resolution text NOT NULL CHECK(resolution IN ('UNRESOLVED','AMBIGUOUS')),
 reason text NOT NULL CHECK(reason ~ '\S'),
 CHECK((binding_status='AMBIGUOUS')=(resolution='AMBIGUOUS')),
 PRIMARY KEY(snapshot_id,entity_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,statement_id) REFERENCES public.ucm_sql_statements(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_sql_access_names (
 snapshot_id uuid NOT NULL, access_id text NOT NULL,
 part text NOT NULL CHECK(part IN ('catalog_name','schema_name','table_name','column_name','qualifier')),
 text text NOT NULL CHECK(char_length(text)>0), quoted boolean NOT NULL,
 normalized text NOT NULL CHECK(char_length(normalized)>0),
 PRIMARY KEY(snapshot_id,access_id,part),
 FOREIGN KEY(snapshot_id,access_id) REFERENCES public.ucm_data_accesses(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER ucm_sql_statements_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_statements
 FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_statements_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_statements
 FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_statement_reasons_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_statement_reasons
 FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_statement_reasons_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_statement_reasons
 FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_data_accesses_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_data_accesses
 FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_data_accesses_truncate_guard BEFORE TRUNCATE ON public.ucm_data_accesses
 FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_access_names_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_access_names
 FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_access_names_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_access_names
 FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
