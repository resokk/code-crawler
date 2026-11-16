CREATE TABLE resolver_contexts (
    id uuid PRIMARY KEY,
    fingerprint text NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE resolver_context_selections (
    context_id uuid NOT NULL REFERENCES resolver_contexts(id) ON DELETE CASCADE,
    repository_id uuid NOT NULL,
    selected_snapshot_id uuid NOT NULL,
    PRIMARY KEY(context_id,repository_id),
    FOREIGN KEY(repository_id,selected_snapshot_id) REFERENCES ucm_snapshots(repository_id,id)
);
CREATE INDEX resolver_context_snapshot_idx ON resolver_context_selections(selected_snapshot_id);
CREATE TABLE resolver_deployments (
    deployment_key text PRIMARY KEY CHECK(deployment_key ~ '\S'),
    fingerprint text NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$')
);
CREATE TABLE resolver_deployment_bindings (
    deployment_key text NOT NULL REFERENCES resolver_deployments(deployment_key) ON DELETE CASCADE,
    service_key text NOT NULL CHECK(service_key ~ '\S'),
    repository_id uuid NOT NULL,
    selected_snapshot_id uuid NOT NULL,
    PRIMARY KEY(deployment_key,service_key),
    FOREIGN KEY(repository_id,selected_snapshot_id) REFERENCES ucm_snapshots(repository_id,id)
);
CREATE INDEX resolver_deployment_snapshot_idx ON resolver_deployment_bindings(selected_snapshot_id);
CREATE FUNCTION resolver_deny_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'resolver manifests are immutable' USING ERRCODE='23514'; END $$;
CREATE TRIGGER resolver_contexts_immutable BEFORE UPDATE ON resolver_contexts FOR EACH ROW EXECUTE FUNCTION resolver_deny_update();
CREATE TRIGGER resolver_selections_immutable BEFORE UPDATE ON resolver_context_selections FOR EACH ROW EXECUTE FUNCTION resolver_deny_update();
CREATE TRIGGER resolver_deployments_immutable BEFORE UPDATE ON resolver_deployments FOR EACH ROW EXECUTE FUNCTION resolver_deny_update();
CREATE TRIGGER resolver_bindings_immutable BEFORE UPDATE ON resolver_deployment_bindings FOR EACH ROW EXECUTE FUNCTION resolver_deny_update();
