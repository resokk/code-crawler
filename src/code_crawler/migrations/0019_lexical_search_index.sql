CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- btree_gin lets one GIN index start with snapshot_id, so search cost does not grow
-- with the number of stored snapshots.
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- "findUserById", "user_id", "app.Repo.load" -> "find user by id", "user id", "app repo load"
CREATE FUNCTION ucm_identifier_words(identifier text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT lower(btrim(regexp_replace(
        regexp_replace(identifier, '([[:lower:][:digit:]])([[:upper:]])', '\1 \2', 'g'),
        '[^[:alnum:]]+', ' ', 'g')))
$$;

CREATE INDEX ucm_entities_name_trgm_idx ON ucm_entities
    USING gin (snapshot_id, lower(name) gin_trgm_ops)
    WHERE entity_type IN ('SYMBOL','SOURCE_FILE','DATABASE_OBJECT','ORM_MAPPING','ORM_QUERY');
CREATE INDEX ucm_entities_name_words_idx ON ucm_entities
    USING gin (snapshot_id, to_tsvector('simple', ucm_identifier_words(name)))
    WHERE entity_type IN ('SYMBOL','SOURCE_FILE','DATABASE_OBJECT','ORM_MAPPING','ORM_QUERY');
CREATE INDEX ucm_symbols_qualified_words_idx ON ucm_symbols
    USING gin (snapshot_id, to_tsvector('simple', ucm_identifier_words(qualified_name)));
