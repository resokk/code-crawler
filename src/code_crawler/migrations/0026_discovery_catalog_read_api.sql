-- Preserve the already-published C02 JSON-key schema and C03 generation contract.
ALTER TABLE public.search_discovery_generations ADD COLUMN state text NOT NULL DEFAULT 'READY'
 CHECK(state IN ('BUILDING','READY'));
CREATE INDEX search_discovery_identifier_idx ON public.search_discovery_entries
 (kind,md5(CASE WHEN kind='DATABASE' THEN COALESCE(lookup_key->>6,lookup_key->>5,lookup_key->>3)
 WHEN kind='HTTP' THEN lookup_key->>2 ELSE lookup_key->>0 END),generation);

CREATE FUNCTION public.guard_discovery_generation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='search_discovery_generations' THEN
  IF TG_OP='DELETE' THEN
   IF current_setting('code_crawler.gc',true)='on' OR current_setting('code_crawler.discovery_build',true)='on' THEN RETURN OLD; END IF;
  ELSIF TG_OP='UPDATE' THEN
   IF OLD.state='BUILDING' AND NEW.state='READY' AND (to_jsonb(NEW)-'state')=(to_jsonb(OLD)-'state') THEN RETURN NEW; END IF;
  ELSIF TG_OP='INSERT' THEN
   IF NEW.state='BUILDING' AND EXISTS (SELECT 1 FROM public.ucm_snapshots WHERE id=NEW.snapshot_id AND state='PUBLISHED') THEN RETURN NEW; END IF;
  END IF;
 ELSE
  IF TG_OP='DELETE' THEN
   IF current_setting('code_crawler.gc',true)='on' OR NOT EXISTS (
    SELECT 1 FROM public.search_discovery_generations WHERE generation=OLD.generation
   ) THEN RETURN OLD; END IF;
  ELSIF TG_OP='INSERT' THEN
   IF EXISTS (SELECT 1 FROM public.search_discovery_generations WHERE generation=NEW.generation AND state='BUILDING') THEN RETURN NEW; END IF;
  END IF;
 END IF;
 RAISE EXCEPTION 'discovery generation is frozen or not published' USING ERRCODE='23514';
END $$;
CREATE TRIGGER search_discovery_generations_guard BEFORE INSERT OR UPDATE OR DELETE
 ON public.search_discovery_generations FOR EACH ROW EXECUTE FUNCTION public.guard_discovery_generation();
CREATE TRIGGER search_discovery_entries_guard BEFORE INSERT OR UPDATE OR DELETE
 ON public.search_discovery_entries FOR EACH ROW EXECUTE FUNCTION public.guard_discovery_generation();
CREATE TRIGGER search_discovery_generations_truncate BEFORE TRUNCATE
 ON public.search_discovery_generations FOR EACH STATEMENT EXECUTE FUNCTION public.guard_discovery_generation();
CREATE TRIGGER search_discovery_entries_truncate BEFORE TRUNCATE
 ON public.search_discovery_entries FOR EACH STATEMENT EXECUTE FUNCTION public.guard_discovery_generation();
