ALTER TABLE public.ucm_entities DROP CONSTRAINT ucm_entities_entity_type_check;
ALTER TABLE public.ucm_entities ADD CHECK(entity_type IN
 ('SOURCE_FILE','CLASS','METHOD','SQL_CANDIDATE','SYMBOL','SCOPE','OCCURRENCE','OPERATION',
 'VALUE','RELATION','EXTERNAL_REFERENCE','SQL_CONSTRUCTION','SQL_EXECUTE','SQL_STATEMENT',
 'DATA_ACCESS','SQL_BINDING','SQL_PLACEHOLDER','DATABASE_CONTEXT','DATABASE_OBJECT','DATABASE_ACCESS',
 'ORM_MAPPING','ORM_QUERY','ORM_OPERATION'));
INSERT INTO public.ucm_relation_sources VALUES
 ('ORM_DECLARES_MAPPING','SYMBOL'),('ORM_HAS_ATTRIBUTE','ORM_MAPPING'),('ORM_DECLARES_QUERY','SYMBOL'),
 ('ORM_NAMED_QUERY','ORM_QUERY'),('ORM_QUERY_ENTITY','ORM_QUERY'),('ORM_QUERY_READS_ATTRIBUTE','ORM_QUERY'),
 ('ORM_QUERY_WRITES_ATTRIBUTE','ORM_QUERY'),('ORM_INVOKES','SYMBOL'),('ORM_TARGET_ENTITY','ORM_OPERATION'),
 ('ORM_EXECUTES_QUERY','ORM_OPERATION'),('ORM_DATABASE_TARGET','ORM_OPERATION');
INSERT INTO public.ucm_relation_endpoints VALUES
 ('ORM_DECLARES_MAPPING','SYMBOL','ORM_MAPPING'),('ORM_HAS_ATTRIBUTE','ORM_MAPPING','ORM_MAPPING'),
 ('ORM_DECLARES_QUERY','SYMBOL','ORM_QUERY'),('ORM_NAMED_QUERY','ORM_QUERY','ORM_QUERY'),
 ('ORM_QUERY_ENTITY','ORM_QUERY','ORM_MAPPING'),('ORM_QUERY_READS_ATTRIBUTE','ORM_QUERY','ORM_MAPPING'),
 ('ORM_QUERY_WRITES_ATTRIBUTE','ORM_QUERY','ORM_MAPPING'),('ORM_INVOKES','SYMBOL','ORM_OPERATION'),
 ('ORM_TARGET_ENTITY','ORM_OPERATION','ORM_MAPPING'),('ORM_EXECUTES_QUERY','ORM_OPERATION','ORM_QUERY'),
 ('ORM_DATABASE_TARGET','ORM_OPERATION','DATABASE_OBJECT');
CREATE TABLE public.ucm_orm_mappings (
 snapshot_id uuid NOT NULL,entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'ORM_MAPPING' CHECK(entity_type='ORM_MAPPING'),
 mapping_kind text NOT NULL CHECK(mapping_kind IN ('ENTITY','ATTRIBUTE')),
 entity_role text NOT NULL CHECK(entity_role IN ('ENTITY','MAPPED_SUPERCLASS','EMBEDDABLE')),
 symbol_id text NOT NULL,owner_symbol_id text NOT NULL,entity_name text NOT NULL CHECK(entity_name ~ '\S'),
 attribute_name text CHECK(attribute_name ~ '\S'),attribute_kind text CHECK(attribute_kind IN ('BASIC','ID','VERSION','RELATIONSHIP','EMBEDDED')),
 access_mode text NOT NULL CHECK(access_mode IN ('FIELD','PROPERTY','UNKNOWN')),
 nullable boolean,insertable boolean,updatable boolean,
 status text NOT NULL CHECK(status IN ('COMPLETE','PARTIAL','UNSUPPORTED')),
 CHECK((mapping_kind='ATTRIBUTE')=(attribute_name IS NOT NULL)),CHECK((mapping_kind='ATTRIBUTE')=(attribute_kind IS NOT NULL)),
 CHECK(mapping_kind<>'ENTITY' OR symbol_id=owner_symbol_id),
 PRIMARY KEY(snapshot_id,entity_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,owner_symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_orm_mapping_names (
 snapshot_id uuid NOT NULL,mapping_id text NOT NULL,
 part text NOT NULL CHECK(part IN ('catalog_name','schema_name','table_name','column_name')),
 text text NOT NULL CHECK(char_length(text)>0),quoted boolean NOT NULL,normalized text NOT NULL CHECK(char_length(normalized)>0),
 PRIMARY KEY(snapshot_id,mapping_id,part),
 FOREIGN KEY(snapshot_id,mapping_id) REFERENCES public.ucm_orm_mappings(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_orm_queries (
 snapshot_id uuid NOT NULL,entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'ORM_QUERY' CHECK(entity_type='ORM_QUERY'),
 owner_symbol_id text NOT NULL,
 query_kind text NOT NULL CHECK(query_kind IN ('JPQL','NATIVE','NAMED_REFERENCE','CRITERIA','UNKNOWN')),
 query_name text CHECK(query_name ~ '\S'),text text CHECK(text ~ '\S'),
 status text NOT NULL CHECK(status IN ('COMPLETE','PARTIAL','UNSUPPORTED')),
 CHECK(query_kind<>'NAMED_REFERENCE' OR text IS NULL),
 PRIMARY KEY(snapshot_id,entity_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,owner_symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_orm_operations (
 snapshot_id uuid NOT NULL,entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'ORM_OPERATION' CHECK(entity_type='ORM_OPERATION'),
 owner_symbol_id text NOT NULL,call_operation_id text NOT NULL,api text NOT NULL CHECK(api ~ '\S'),
 operation_kind text NOT NULL CHECK(operation_kind IN ('PERSIST','MERGE','REMOVE','FIND','GET_REFERENCE','REFRESH','FLUSH','QUERY_READ','QUERY_WRITE')),
 effect_kind text NOT NULL CHECK(effect_kind IN ('READ','INSERT','MERGE','DELETE','WRITE','REFERENCE','UNKNOWN')),
 query_id text,context_id text,
 PRIMARY KEY(snapshot_id,entity_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,owner_symbol_id) REFERENCES public.ucm_symbols(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,call_operation_id) REFERENCES public.ucm_operations(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,query_id) REFERENCES public.ucm_orm_queries(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,context_id) REFERENCES public.ucm_database_contexts(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_orm_reasons (
 snapshot_id uuid NOT NULL,owner_id text NOT NULL,ordinal integer NOT NULL CHECK(ordinal>=0),reason text NOT NULL CHECK(reason ~ '\S'),
 PRIMARY KEY(snapshot_id,owner_id,ordinal),
 FOREIGN KEY(snapshot_id,owner_id) REFERENCES public.ucm_entities(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER ucm_orm_mappings_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_orm_mappings FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_mappings_truncate BEFORE TRUNCATE ON public.ucm_orm_mappings FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_names_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_orm_mapping_names FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_names_truncate BEFORE TRUNCATE ON public.ucm_orm_mapping_names FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_queries_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_orm_queries FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_queries_truncate BEFORE TRUNCATE ON public.ucm_orm_queries FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_operations_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_orm_operations FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_operations_truncate BEFORE TRUNCATE ON public.ucm_orm_operations FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_reasons_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_orm_reasons FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_orm_reasons_truncate BEFORE TRUNCATE ON public.ucm_orm_reasons FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
