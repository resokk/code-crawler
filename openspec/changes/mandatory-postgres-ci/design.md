# Design

Use GitHub Actions service postgres:15 with CREATEDB and a healthcheck, Python 3.12,
pinned uv and locked dependencies. Apply migrations using existing CLI to a clean
service DB, then run all tests; isolated integration fixture DBs remain unchanged.

Pytest policy detects CI/explicit mandatory mode, requires TEST_DATABASE_URL and
selected integration tests, and converts skipped integration reports to failures.
Policy regression tests run isolated subprocess sessions with actual plugin code.

Git working-tree drift check runs even on previous failures, collecting status/diff.
Capture logs/JUnit and PostgreSQL service output and upload failure artifacts.
Required branch status is configured separately in GitHub repository settings;
workflow permissions remain contents:read. Document stable check name and pending
hosted verification rather than claiming local tests enabled branch protection.
