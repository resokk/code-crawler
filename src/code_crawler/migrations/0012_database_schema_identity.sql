CREATE TABLE public.ucm_database_catalogs (
 database_key text PRIMARY KEY CHECK(database_key ~ '\S')
);
CREATE TABLE public.ucm_database_schema_versions (
 database_key text NOT NULL REFERENCES public.ucm_database_catalogs(database_key),
 version_key text NOT NULL CHECK(version_key ~ '\S'),
 dialect text NOT NULL CHECK(dialect IN ('postgres','mysql','tsql')),
 catalog_name text NOT NULL CHECK(char_length(catalog_name)>0),
 table_case text NOT NULL CHECK(table_case IN ('EXACT','ASCII_INSENSITIVE')),
 column_case text NOT NULL CHECK(column_case IN ('EXACT','ASCII_INSENSITIVE')),
 coverage text NOT NULL CHECK(coverage IN ('COMPLETE','PARTIAL')),
 fingerprint text NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
 state text NOT NULL DEFAULT 'BUILDING' CHECK(state IN ('BUILDING','READY')),
 PRIMARY KEY(database_key,version_key), UNIQUE(database_key,version_key,fingerprint)
);
CREATE TABLE public.ucm_database_schema_objects (
 object_key text PRIMARY KEY CHECK(object_key ~ '^db:[0-9a-f]{64}$'),
 database_key text NOT NULL, version_key text NOT NULL,
 object_kind text NOT NULL CHECK(object_kind IN ('SCHEMA','TABLE','VIEW','MATERIALIZED_VIEW','FOREIGN_TABLE','COLUMN')),
 schema_name text NOT NULL CHECK(char_length(schema_name)>0),
 table_name text CHECK(char_length(table_name)>0),column_name text CHECK(char_length(column_name)>0),
 parent_key text, ordinal integer CHECK(ordinal>=1), data_type text CHECK(data_type ~ '\S'),
 nullable boolean, primary_key boolean,
 CHECK((object_kind='COLUMN')=(column_name IS NOT NULL)),
 CHECK((object_kind<>'SCHEMA')=(table_name IS NOT NULL)),
 CHECK((object_kind<>'SCHEMA')=(parent_key IS NOT NULL)),
 CHECK((object_kind='COLUMN')=(ordinal IS NOT NULL AND data_type IS NOT NULL AND nullable IS NOT NULL AND primary_key IS NOT NULL)),
 CHECK(object_kind='COLUMN' OR (ordinal IS NULL AND data_type IS NULL AND nullable IS NULL AND primary_key IS NULL)),
 UNIQUE(database_key,version_key,object_key),
 FOREIGN KEY(database_key,version_key) REFERENCES public.ucm_database_schema_versions(database_key,version_key),
 FOREIGN KEY(database_key,version_key,parent_key) REFERENCES public.ucm_database_schema_objects(database_key,version_key,object_key) DEFERRABLE INITIALLY DEFERRED
);
CREATE FUNCTION public.ucm_guard_schema_inventory() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE version_state text;
BEGIN
 IF TG_OP='TRUNCATE' OR TG_OP='DELETE' THEN
  RAISE EXCEPTION 'database inventory is immutable' USING ERRCODE='23514';
 END IF;
 IF TG_TABLE_NAME='ucm_database_schema_versions' THEN
  IF TG_OP='INSERT' AND NEW.state='BUILDING' THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' AND OLD.state='BUILDING' AND NEW.state='READY'
     AND (to_jsonb(NEW)-'state')=(to_jsonb(OLD)-'state') THEN RETURN NEW; END IF;
  RAISE EXCEPTION 'invalid schema version mutation' USING ERRCODE='23514';
 ELSIF TG_TABLE_NAME='ucm_database_schema_objects' THEN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'schema objects are immutable' USING ERRCODE='23514'; END IF;
  SELECT state INTO version_state FROM public.ucm_database_schema_versions
   WHERE database_key=NEW.database_key AND version_key=NEW.version_key FOR SHARE;
  IF version_state IS DISTINCT FROM 'BUILDING' THEN
   RAISE EXCEPTION 'schema objects require BUILDING import' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 ELSIF TG_OP='INSERT' THEN RETURN NEW;
 ELSE RAISE EXCEPTION 'database identity is immutable' USING ERRCODE='23514';
 END IF;
END $$;
CREATE TRIGGER ucm_database_catalogs_guard BEFORE UPDATE OR DELETE ON public.ucm_database_catalogs FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_schema_inventory();
CREATE TRIGGER ucm_database_catalogs_truncate BEFORE TRUNCATE ON public.ucm_database_catalogs FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_schema_inventory();
CREATE TRIGGER ucm_database_versions_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_database_schema_versions FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_schema_inventory();
CREATE TRIGGER ucm_database_versions_truncate BEFORE TRUNCATE ON public.ucm_database_schema_versions FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_schema_inventory();
CREATE TRIGGER ucm_database_inventory_guard BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_database_schema_objects FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_schema_inventory();
CREATE TRIGGER ucm_database_inventory_truncate BEFORE TRUNCATE ON public.ucm_database_schema_objects FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_schema_inventory();
ALTER TABLE public.ucm_entities DROP CONSTRAINT ucm_entities_entity_type_check;
ALTER TABLE public.ucm_entities ADD CHECK(entity_type IN
 ('SOURCE_FILE','CLASS','METHOD','SQL_CANDIDATE','SYMBOL','SCOPE','OCCURRENCE','OPERATION',
 'VALUE','RELATION','EXTERNAL_REFERENCE','SQL_CONSTRUCTION','SQL_EXECUTE','SQL_STATEMENT',
 'DATA_ACCESS','SQL_BINDING','SQL_PLACEHOLDER','DATABASE_CONTEXT','DATABASE_OBJECT','DATABASE_ACCESS'));
INSERT INTO public.ucm_relation_sources VALUES ('USES_DATABASE_CONTEXT','SQL_EXECUTE'),('CONTEXTUALIZES_ACCESS','DATA_ACCESS'),('IN_DATABASE_CONTEXT','DATABASE_ACCESS'),('RESOLVES_DATABASE_OBJECT','DATABASE_ACCESS');
INSERT INTO public.ucm_relation_endpoints VALUES ('USES_DATABASE_CONTEXT','SQL_EXECUTE','DATABASE_CONTEXT'),('CONTEXTUALIZES_ACCESS','DATA_ACCESS','DATABASE_ACCESS'),('IN_DATABASE_CONTEXT','DATABASE_ACCESS','DATABASE_CONTEXT'),('RESOLVES_DATABASE_OBJECT','DATABASE_ACCESS','DATABASE_OBJECT');
CREATE TABLE public.ucm_database_objects (
 snapshot_id uuid NOT NULL,entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'DATABASE_OBJECT' CHECK(entity_type='DATABASE_OBJECT'),
 projection_file_id text NOT NULL,database_key text NOT NULL,version_key text NOT NULL,
 schema_fingerprint text NOT NULL,object_key text NOT NULL,
 object_kind text NOT NULL CHECK(object_kind IN ('SCHEMA','TABLE','VIEW','MATERIALIZED_VIEW','FOREIGN_TABLE','COLUMN')),
 catalog_name text NOT NULL CHECK(char_length(catalog_name)>0),schema_name text NOT NULL CHECK(char_length(schema_name)>0),
 table_name text CHECK(char_length(table_name)>0),column_name text CHECK(char_length(column_name)>0),
 CHECK((object_kind='COLUMN')=(column_name IS NOT NULL)),CHECK((object_kind<>'SCHEMA')=(table_name IS NOT NULL)),
 PRIMARY KEY(snapshot_id,entity_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,projection_file_id) REFERENCES public.ucm_source_files(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(database_key,version_key,object_key) REFERENCES public.ucm_database_schema_objects(database_key,version_key,object_key),
 FOREIGN KEY(database_key,version_key,schema_fingerprint) REFERENCES public.ucm_database_schema_versions(database_key,version_key,fingerprint)
);
CREATE TABLE public.ucm_database_contexts (
 snapshot_id uuid NOT NULL,entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'DATABASE_CONTEXT' CHECK(entity_type='DATABASE_CONTEXT'),
 projection_file_id text NOT NULL,connection_key text NOT NULL CHECK(connection_key ~ '\S'),
 database_key text NOT NULL,version_key text NOT NULL,schema_fingerprint text NOT NULL,
 PRIMARY KEY(snapshot_id,entity_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,projection_file_id) REFERENCES public.ucm_source_files(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(database_key,version_key,schema_fingerprint) REFERENCES public.ucm_database_schema_versions(database_key,version_key,fingerprint)
);
CREATE TABLE public.ucm_database_search_paths (
 snapshot_id uuid NOT NULL,context_id text NOT NULL,position integer NOT NULL CHECK(position>=0),
 schema_name text NOT NULL CHECK(char_length(schema_name)>0),PRIMARY KEY(snapshot_id,context_id,position),
 UNIQUE(snapshot_id,context_id,schema_name),
 FOREIGN KEY(snapshot_id,context_id) REFERENCES public.ucm_database_contexts(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_database_accesses (
 snapshot_id uuid NOT NULL,entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'DATABASE_ACCESS' CHECK(entity_type='DATABASE_ACCESS'),
 access_id text NOT NULL,context_id text,execution_id text,
 PRIMARY KEY(snapshot_id,entity_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,access_id) REFERENCES public.ucm_data_accesses(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,context_id) REFERENCES public.ucm_database_contexts(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,execution_id) REFERENCES public.ucm_sql_executions(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE FUNCTION public.ucm_guard_database_projection() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE version_state text;
BEGIN
 SELECT state INTO version_state FROM public.ucm_database_schema_versions
 WHERE database_key=NEW.database_key AND version_key=NEW.version_key;
 IF version_state IS DISTINCT FROM 'READY' THEN
  RAISE EXCEPTION 'database projection requires READY inventory' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ucm_database_objects_ready BEFORE INSERT OR UPDATE ON public.ucm_database_objects FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_database_projection();
CREATE TRIGGER ucm_database_contexts_ready BEFORE INSERT OR UPDATE ON public.ucm_database_contexts FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_database_projection();
CREATE TRIGGER ucm_database_objects_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_database_objects FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_database_objects_truncate BEFORE TRUNCATE ON public.ucm_database_objects FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_database_contexts_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_database_contexts FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_database_contexts_truncate BEFORE TRUNCATE ON public.ucm_database_contexts FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_database_paths_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_database_search_paths FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_database_paths_truncate BEFORE TRUNCATE ON public.ucm_database_search_paths FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_database_accesses_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_database_accesses FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_database_accesses_truncate BEFORE TRUNCATE ON public.ucm_database_accesses FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
