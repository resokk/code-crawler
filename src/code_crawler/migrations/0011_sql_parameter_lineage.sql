ALTER TABLE public.ucm_entities DROP CONSTRAINT ucm_entities_entity_type_check;
ALTER TABLE public.ucm_entities ADD CHECK (entity_type IN
 ('SOURCE_FILE','CLASS','METHOD','SQL_CANDIDATE','SYMBOL','SCOPE','OCCURRENCE','OPERATION',
 'VALUE','RELATION','EXTERNAL_REFERENCE','SQL_CONSTRUCTION','SQL_EXECUTE','SQL_STATEMENT',
 'DATA_ACCESS','SQL_BINDING','SQL_PLACEHOLDER'));
INSERT INTO public.ucm_relation_sources VALUES
 ('HAS_SQL_BINDING','SQL_EXECUTE'),('VALUE_BINDS_SQL','VALUE'),('BINDS_PARAMETER','SQL_BINDING'),
 ('PARAMETER_COLUMN','SQL_PLACEHOLDER'),('HAS_SQL_PARAMETER','SQL_STATEMENT'),('VALUE_OF','VALUE');
INSERT INTO public.ucm_relation_endpoints VALUES
 ('HAS_SQL_BINDING','SQL_EXECUTE','SQL_BINDING'),('VALUE_BINDS_SQL','VALUE','SQL_BINDING'),
 ('BINDS_PARAMETER','SQL_BINDING','SQL_PLACEHOLDER'),('PARAMETER_COLUMN','SQL_PLACEHOLDER','DATA_ACCESS'),
 ('HAS_SQL_PARAMETER','SQL_STATEMENT','SQL_PLACEHOLDER'),('VALUE_OF','VALUE','SYMBOL');
CREATE TABLE public.ucm_sql_placeholders (
 snapshot_id uuid NOT NULL, entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'SQL_PLACEHOLDER' CHECK(entity_type='SQL_PLACEHOLDER'),
 statement_id text NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=1),
 parameter_kind text NOT NULL CHECK(parameter_kind IN ('POSITIONAL','INDEXED','NAMED')),
 position integer CHECK(position>=1), parameter_name text CHECK(parameter_name ~ '\S'),
 token_text text NOT NULL CHECK(token_text ~ '\S'),
 text_start integer NOT NULL CHECK(text_start>=0), text_end integer NOT NULL CHECK(text_end>text_start),
 CHECK(text_end-text_start=char_length(token_text)),
 CHECK((parameter_kind='NAMED')=(parameter_name IS NOT NULL)),
 CHECK((parameter_kind<>'NAMED')=(position IS NOT NULL)),
 PRIMARY KEY(snapshot_id,entity_id), UNIQUE(snapshot_id,statement_id,ordinal),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,statement_id) REFERENCES public.ucm_sql_statements(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_sql_bindings (
 snapshot_id uuid NOT NULL, entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'SQL_BINDING' CHECK(entity_type='SQL_BINDING'),
 execution_id text NOT NULL, value_id text NOT NULL, setter_operation_id text,
 api text NOT NULL CHECK(api ~ '\S'),
 binding_kind text NOT NULL CHECK(binding_kind IN ('POSITIONAL','NAMED','UNKNOWN')),
 position integer CHECK(position>=1), parameter_name text CHECK(parameter_name ~ '\S'),
 status text NOT NULL CHECK(status IN ('BOUND','PARTIAL','MISSING','UNKNOWN')),
 CHECK((binding_kind='POSITIONAL')=(position IS NOT NULL)),
 CHECK((binding_kind='NAMED')=(parameter_name IS NOT NULL)),
 PRIMARY KEY(snapshot_id,entity_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,execution_id) REFERENCES public.ucm_sql_executions(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,value_id) REFERENCES public.ucm_values(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,setter_operation_id) REFERENCES public.ucm_operations(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_sql_binding_reasons (
 snapshot_id uuid NOT NULL, binding_id text NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=0),
 reason text NOT NULL CHECK(reason ~ '\S'), PRIMARY KEY(snapshot_id,binding_id,ordinal),
 FOREIGN KEY(snapshot_id,binding_id) REFERENCES public.ucm_sql_bindings(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER ucm_sql_placeholders_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_placeholders
 FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_placeholders_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_placeholders
 FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_bindings_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_bindings
 FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_bindings_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_bindings
 FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_binding_reasons_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_binding_reasons
 FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_binding_reasons_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_binding_reasons
 FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
