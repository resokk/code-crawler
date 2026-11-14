# Mandatory PostgreSQL CI

Workflow `.github/workflows/ci.yml` (`CI`) запускается для pull requests, push в
main и workflow_dispatch. Один стабильный check `PostgreSQL 15` использует Python
3.12, pinned uv, `uv sync --locked`, PostgreSQL 15 service с healthcheck и отдельную
тестовую БД. Job имеет read-only contents permission и не обращается к production DB.

Порядок: Ruff check/format → все migrations через CLI db init/status на чистой БД →
полный pytest (unit/integration/regression) с `--require-postgres` и JUnit → проверка
чистоты Git working tree. Integration fixtures по-прежнему создают/удаляют собственные
уникальные БД; PostgreSQL service user имеет CREATEDB. Ошибки связи/версии/прав — failure.

Pytest policy в `tests/ci_postgres.py` включается флагом `--require-postgres`,
`CI=true|1` или `GITHUB_ACTIONS=true|1`. В этом режиме:

- пустой TEST_DATABASE_URL — usage error до тестов;
- отсутствие выбранных integration tests — usage error; `--collect-only` без
  исполнения integration tests также не даёт успешного check;
- любой skip/xfail integration test — failed report, а не зелёный job.

Локальный `uv run pytest` без этих признаков сохраняет opt-in PostgreSQL; можно
запускать unit-only suite. Полный обязательный запуск локально:

```sh
TEST_DATABASE_URL=postgresql://postgres:integration@127.0.0.1:55432/postgres \
  uv run pytest --require-postgres
```

JUnit, pytest/lint/migration logs, git status/diff и PostgreSQL service log при
failure сохраняются artifact на 7 дней. Reports пишутся в ignored `.ci-reports/`;
artifact включает patch изменённых tracked files; dumps БД и environment
не создаются. Проверка
working tree учитывает tracked изменения и новые неигнорируемые файлы, включая
ANTLR-generated sources и schema exports. Изменения tests не должны оставлять
новые generated artifacts в checkout.

Для блокировки merge требуется repository rule/branch protection для main с
required status check **PostgreSQL 15** workflow **CI**. Сам workflow не может
включить branch protection. Настройка и первый hosted run выполняются после push;
наличие workflow в Git не является доказательством успешного remote CI. Не включать
paths filters, которые оставят required check отсутствующим для части PR.

Контракт OpenSpec: mandatory-postgres-ci; порядок разработки:
[development-plan-v2.md](development-plan-v2.md).
