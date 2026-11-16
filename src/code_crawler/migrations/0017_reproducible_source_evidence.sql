LOCK TABLE ucm_snapshots IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE ucm_source_blobs (
 repository_id uuid NOT NULL REFERENCES ucm_repositories(id),
 content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[0-9a-f]{64}$'),
 content bytea NOT NULL,
 PRIMARY KEY(repository_id,content_sha256),
 CHECK(encode(sha256(content),'hex')=content_sha256)
);
CREATE FUNCTION ucm_guard_source_blob() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP <> 'INSERT' THEN
  RAISE EXCEPTION 'source blobs are immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER ucm_source_blob_write_guard BEFORE UPDATE OR DELETE ON ucm_source_blobs
 FOR EACH ROW EXECUTE FUNCTION ucm_guard_source_blob();
CREATE TRIGGER ucm_source_blob_truncate_guard BEFORE TRUNCATE ON ucm_source_blobs
 FOR EACH STATEMENT EXECUTE FUNCTION ucm_guard_source_blob();

CREATE TABLE ucm_snapshot_sources (
 snapshot_id uuid NOT NULL,
 source_file_id text NOT NULL,
 repository_id uuid NOT NULL,
 content_sha256 text NOT NULL,
 origin text NOT NULL CHECK(origin IN ('CAPTURED_WORKTREE','PROVIDED_BYTES')),
 PRIMARY KEY(snapshot_id,source_file_id),
 FOREIGN KEY(snapshot_id,source_file_id) REFERENCES ucm_source_files(snapshot_id,entity_id),
 FOREIGN KEY(repository_id,snapshot_id) REFERENCES ucm_snapshots(repository_id,id),
 FOREIGN KEY(repository_id,content_sha256) REFERENCES ucm_source_blobs(repository_id,content_sha256)
);
CREATE TRIGGER ucm_snapshot_source_write_guard BEFORE INSERT OR UPDATE OR DELETE ON ucm_snapshot_sources
 FOR EACH ROW EXECUTE FUNCTION ucm_guard_fact_write();
CREATE TRIGGER ucm_snapshot_source_truncate_guard BEFORE TRUNCATE ON ucm_snapshot_sources
 FOR EACH STATEMENT EXECUTE FUNCTION ucm_guard_fact_write();
CREATE FUNCTION ucm_check_source_link() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM ucm_source_files f WHERE f.snapshot_id=NEW.snapshot_id
   AND f.entity_id=NEW.source_file_id AND f.content_sha256=NEW.content_sha256) THEN
  RAISE EXCEPTION 'source blob must match SourceFile hash' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER ucm_source_link_hash_guard BEFORE INSERT OR UPDATE ON ucm_snapshot_sources
 FOR EACH ROW EXECUTE FUNCTION ucm_check_source_link();

CREATE TABLE ucm_source_evidence_legacy_snapshots (
 snapshot_id uuid PRIMARY KEY REFERENCES ucm_snapshots(id)
);
INSERT INTO ucm_source_evidence_legacy_snapshots(snapshot_id)
 SELECT id FROM ucm_snapshots WHERE state IN ('PUBLISHED','RETIRED');
CREATE FUNCTION ucm_guard_legacy_source_exemption() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' AND current_setting('code_crawler.gc', true)='on' AND EXISTS(
   SELECT 1 FROM ucm_snapshots WHERE id=OLD.snapshot_id AND state='RETIRED') THEN
  RETURN OLD;
 END IF;
 RAISE EXCEPTION 'legacy source exemptions are immutable migration data' USING ERRCODE='23514';
END;
$$;
CREATE TRIGGER ucm_legacy_source_exemption_write_guard BEFORE INSERT OR UPDATE OR DELETE ON ucm_source_evidence_legacy_snapshots
 FOR EACH ROW EXECUTE FUNCTION ucm_guard_legacy_source_exemption();
CREATE TRIGGER ucm_legacy_source_exemption_truncate_guard BEFORE TRUNCATE ON ucm_source_evidence_legacy_snapshots
 FOR EACH STATEMENT EXECUTE FUNCTION ucm_guard_legacy_source_exemption();

CREATE FUNCTION ucm_require_source_archive() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.state IN ('READY','PUBLISHED') AND NOT EXISTS(
   SELECT 1 FROM ucm_source_evidence_legacy_snapshots WHERE snapshot_id=NEW.id)
 AND EXISTS(SELECT 1 FROM ucm_source_files f LEFT JOIN ucm_snapshot_sources a
   ON a.snapshot_id=f.snapshot_id AND a.source_file_id=f.entity_id AND a.content_sha256=f.content_sha256
   WHERE f.snapshot_id=NEW.id AND a.source_file_id IS NULL) THEN
  RAISE EXCEPTION 'snapshot requires complete archived source bytes' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER ucm_snapshot_source_archive_guard BEFORE UPDATE OF state ON ucm_snapshots
 FOR EACH ROW EXECUTE FUNCTION ucm_require_source_archive();
