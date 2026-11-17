CREATE TABLE operational_observations (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 repository_id uuid REFERENCES ucm_repositories(id),
 job_id uuid,
 attempt integer NOT NULL CHECK (attempt >= 1),
 stage text NOT NULL CHECK (stage IN ('index','analyze','prepare','stage','transfer','fk','validate','publish','gc','search','db')),
 calls bigint NOT NULL CHECK (calls >= 0),
 errors bigint NOT NULL CHECK (errors >= 0),
 seconds double precision NOT NULL CHECK (seconds >= 0 AND seconds < 'Infinity'::float8),
 rows bigint NOT NULL CHECK (rows >= 0),
 truncated bigint NOT NULL CHECK (truncated >= 0),
 cache_hits bigint NOT NULL CHECK (cache_hits >= 0),
 cache_misses bigint NOT NULL CHECK (cache_misses >= 0),
 peak_rss_bytes bigint NOT NULL CHECK (peak_rss_bytes >= 0)
);
CREATE INDEX operational_observations_scope_time ON operational_observations(repository_id, recorded_at);
