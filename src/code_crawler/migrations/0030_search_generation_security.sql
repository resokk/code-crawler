-- Security diagnostics belong to a derivative generation, not canonical Evidence.
ALTER TABLE public.search_index_generations
    ADD COLUMN security_report jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(security_report) = 'object');
