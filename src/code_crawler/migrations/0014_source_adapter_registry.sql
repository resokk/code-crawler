ALTER TABLE public.ucm_entities DROP CONSTRAINT ucm_entities_entity_type_check;
ALTER TABLE public.ucm_entities ADD CHECK(entity_type IN
 ('SOURCE_FILE','CLASS','METHOD','SQL_CANDIDATE','SYMBOL','SCOPE','OCCURRENCE','OPERATION',
 'VALUE','RELATION','EXTERNAL_REFERENCE','SQL_CONSTRUCTION','SQL_EXECUTE','SQL_STATEMENT',
 'DATA_ACCESS','SQL_BINDING','SQL_PLACEHOLDER','DATABASE_CONTEXT','DATABASE_OBJECT','DATABASE_ACCESS',
 'ORM_MAPPING','ORM_QUERY','ORM_OPERATION','SOURCE_ANALYSIS'));
CREATE TABLE public.ucm_source_analyses (
 snapshot_id uuid NOT NULL,entity_id text NOT NULL,
 entity_type text NOT NULL DEFAULT 'SOURCE_ANALYSIS' CHECK(entity_type='SOURCE_ANALYSIS'),
 source_file_id text NOT NULL,adapter_key text NOT NULL CHECK(adapter_key ~ '\S'),
 adapter_version text NOT NULL CHECK(adapter_version ~ '\S'),analysis_version text NOT NULL CHECK(analysis_version ~ '\S'),
 PRIMARY KEY(snapshot_id,entity_id),UNIQUE(snapshot_id,source_file_id),
 FOREIGN KEY(snapshot_id,entity_id,entity_type) REFERENCES public.ucm_entities(snapshot_id,entity_id,entity_type) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,source_file_id) REFERENCES public.ucm_source_files(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_source_analysis_capabilities (
 snapshot_id uuid NOT NULL,analysis_id text NOT NULL,capability text NOT NULL CHECK(capability ~ '\S'),
 analyzer_version text NOT NULL CHECK(analyzer_version ~ '\S'),
 status text NOT NULL CHECK(status IN ('COMPLETE','PARTIAL','UNSUPPORTED')),
 PRIMARY KEY(snapshot_id,analysis_id,capability),
 FOREIGN KEY(snapshot_id,analysis_id) REFERENCES public.ucm_source_analyses(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_source_analysis_reasons (
 snapshot_id uuid NOT NULL,analysis_id text NOT NULL,capability text NOT NULL,
 ordinal integer NOT NULL CHECK(ordinal>=0),reason text NOT NULL CHECK(reason ~ '\S'),
 PRIMARY KEY(snapshot_id,analysis_id,capability,ordinal),
 FOREIGN KEY(snapshot_id,analysis_id,capability) REFERENCES public.ucm_source_analysis_capabilities(snapshot_id,analysis_id,capability) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE public.ucm_source_diagnostics (
 snapshot_id uuid NOT NULL,analysis_id text NOT NULL,ordinal integer NOT NULL CHECK(ordinal>=0),
 severity text NOT NULL CHECK(severity IN ('ERROR','WARNING','INFO')),code text NOT NULL CHECK(code ~ '\S'),message text NOT NULL CHECK(message ~ '\S'),
 source_file_id text,start_line integer,start_byte_column integer,end_line integer,end_byte_column integer,
 CHECK((source_file_id IS NULL AND start_line IS NULL AND start_byte_column IS NULL AND end_line IS NULL AND end_byte_column IS NULL)
  OR (source_file_id IS NOT NULL AND start_line IS NOT NULL AND start_byte_column IS NOT NULL AND end_line IS NOT NULL AND end_byte_column IS NOT NULL AND start_line>=1 AND start_byte_column>=0 AND end_line>=1 AND end_byte_column>=0 AND (start_line,start_byte_column)<=(end_line,end_byte_column))),
 PRIMARY KEY(snapshot_id,analysis_id,ordinal),
 FOREIGN KEY(snapshot_id,analysis_id) REFERENCES public.ucm_source_analyses(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(snapshot_id,source_file_id) REFERENCES public.ucm_source_files(snapshot_id,entity_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER ucm_source_analyses_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_source_analyses FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_analyses_truncate BEFORE TRUNCATE ON public.ucm_source_analyses FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_capabilities_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_source_analysis_capabilities FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_capabilities_truncate BEFORE TRUNCATE ON public.ucm_source_analysis_capabilities FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_reasons_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_source_analysis_reasons FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_reasons_truncate BEFORE TRUNCATE ON public.ucm_source_analysis_reasons FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_diagnostics_write BEFORE INSERT OR UPDATE OR DELETE ON public.ucm_source_diagnostics FOR EACH ROW EXECUTE FUNCTION public.ucm_guard_fact_write();
CREATE TRIGGER ucm_source_diagnostics_truncate BEFORE TRUNCATE ON public.ucm_source_diagnostics FOR EACH STATEMENT EXECUTE FUNCTION public.ucm_guard_fact_write();
