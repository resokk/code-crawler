ALTER TABLE public.ucm_entities DROP CONSTRAINT ucm_entities_entity_type_check;
ALTER TABLE public.ucm_entities ADD CHECK (entity_type IN
    ('SOURCE_FILE','CLASS','METHOD','SQL_CANDIDATE','SYMBOL','SCOPE','OCCURRENCE',
     'OPERATION','VALUE','RELATION','EXTERNAL_REFERENCE','SQL_CONSTRUCTION','SQL_EXECUTE'));
INSERT INTO public.ucm_relation_sources VALUES ('EXECUTES_SQL','SYMBOL'),('USES_SQL_CONSTRUCTION','SQL_EXECUTE');
INSERT INTO public.ucm_relation_endpoints VALUES ('EXECUTES_SQL','SYMBOL','SQL_EXECUTE'),('USES_SQL_CONSTRUCTION','SQL_EXECUTE','SQL_CONSTRUCTION');
CREATE TABLE public.ucm_sql_executions (
    snapshot_id uuid NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL DEFAULT 'SQL_EXECUTE' CHECK(entity_type='SQL_EXECUTE'),
    owner_symbol_id text NOT NULL,
    operation_id text NOT NULL,
    api text NOT NULL CHECK(api ~ '\S'),
    sql_argument_index integer CHECK(sql_argument_index>=0),
    PRIMARY KEY(snapshot_id,entity_id),
    FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(snapshot_id,owner_symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(snapshot_id,operation_id) REFERENCES public.ucm_operations(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER ucm_sql_executions_write_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_sql_executions
    FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_sql_executions_truncate_guard BEFORE TRUNCATE ON public.ucm_sql_executions
    FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
