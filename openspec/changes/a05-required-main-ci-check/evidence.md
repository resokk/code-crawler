# A05 evidence — 2026-11-15

Status: partially prepared, external acceptance blocked by API permissions.

- `GET /repos/resokk/code-crawler/branches/main/protection`: HTTP 403,
  `Resource not accessible by integration`.
- `GET /repos/resokk/code-crawler/rulesets`: HTTP 200, `[]`.
- Repository metadata reports `permissions.admin=true`; this does not prove
  the integration token has Administration endpoint permission.
- Check run on `c831584a3d68ce4c9389aaa065af1432bb110bcc`: name
  `PostgreSQL 15`, app `github-actions`, app ID 15368, conclusion success.
  https://github.com/resokk/code-crawler/actions/runs/43684854325
- Workflow `CI` has unfiltered pull_request, main push and workflow_dispatch
  triggers; job `postgres15` has stable name `PostgreSQL 15`.
- Exact administrator setup payload and positive/negative verification steps:
  docs/ci.md, section A05. No repository rule was changed; no failing test PR
  was created while enforcement cannot be inspected.

Remaining: administrator applies/verifies protection, saves rule URL/API output,
and validates failing, missing and successful checks on a temporary unmerged PR.
A05 remains active. No new application types, schema migration or UCM behavior.

Local documentation-change validation: Ruff check and format check passed;
pytest: 958 passed, 167 skipped without TEST_DATABASE_URL. This run does not
constitute mandatory PostgreSQL or branch-enforcement acceptance.

Update 2026-11-15: an administrator token enabled classic branch protection on
`main` with required check `PostgreSQL 15` (app ID 15368), strict, and
`enforce_admins=false` (`enforcement_level: non_admins`). This is weaker than the
A05 ruleset: administrators bypass it and no pull request is required. The
no-bypass ruleset and the failing/missing/successful PR checks remain open.
