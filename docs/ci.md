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

## A05: настройка required check администратором

Проверка 2026-11-15: `GET /repos/resokk/code-crawler/branches/main/protection`
возвращает `403 Resource not accessible by integration`; список repository rulesets
через `GET /repos/resokk/code-crawler/rulesets` пуст (`[]`). Это не подтверждает
отсутствие classic protection: её конфигурация недоступна текущей интеграции.
Поле `permissions.admin=true` в metadata репозитория не гарантирует доступ токена
к endpoint Administration. A05 остаётся открытым до проверки enforcement.

Фактический check из успешного запуска PR #7:
`PostgreSQL 15`, приложение `github-actions`, integration ID `15368`, workflow `CI`.
[Успешный запуск](https://github.com/resokk/code-crawler/actions/runs/43684854325)
подтверждает исполнение тестов, но не обязательность статуса для merge.

Администратор с доступом **Administration: write** должен открыть
[Settings → Rules → Rulesets](https://github.com/resokk/code-crawler/settings/rules),
проверить существующие classic/organization rules и создать branch ruleset:

- target: branch, include `refs/heads/main`, enforcement **Active**;
- bypass list пуст, включая администраторов и интеграции;
- require a pull request before merging;
- require status checks: **PostgreSQL 15**, source **GitHub Actions**;
- require branches to be up to date before merging;
- не добавлять path filters к workflow CI.

Эквивалентный payload для создания отдельного repository ruleset (сохранить как
`/tmp/code-crawler-required-ci.json`; команда требует административного токена):

```json
{
  "name": "main-required-postgres-ci",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {"include": ["refs/heads/main"], "exclude": []}
  },
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "PostgreSQL 15", "integration_id": 15368}
        ]
      }
    }
  ]
}
```

```sh
gh api --method POST repos/resokk/code-crawler/rulesets \
  --input /tmp/code-crawler-required-ci.json \
  --jq '{id, name, enforcement, url: ._links.html.href}'
gh api repos/resokk/code-crawler/rules/branches/main
# Substitute the returned ruleset ID:
gh api repos/resokk/code-crawler/rulesets/RULESET_ID
```

Создавать правило следует один раз, после сверки существующих ограничений;
эти команды не запускаются самим CI и не заменяют существующие правила.
Не сохранять токен или вывод environment в репозиторий.

### Контролируемая проверка enforcement

После настройки создать отдельный временный PR в main; **не выполнять merge**.
Зафиксировать URL ruleset, PR, head SHA, check run и вывод
`gh pr checks PR_NUMBER --required` для каждого состояния:

1. Добавить в тестовую ветку завершающийся с `exit 1` шаг существующего job
   `postgres15`. Дождаться красного **PostgreSQL 15**. Проверить, что GitHub UI
   запрещает обычный merge и API PR показывает blocked merge state.
2. В той же тестовой ветке временно переименовать job check, сохранив workflow
   и исполнение тестов. Новый head SHA не должен иметь check **PostgreSQL 15**;
   required check должен ожидаться, merge оставаться заблокированным.
3. Восстановить workflow целиком. Дождаться успешного **PostgreSQL 15** на
   актуальном head и подтвердить, что требование статуса выполнено. Другие
   правила могут продолжать блокировать merge; это нужно указать отдельно.
4. Закрыть временный PR без merge. Сохранить обезличенный вывод API и ссылки
   в evidence A05; не считать прошлый зелёный PR проверкой отрицательных случаев.

До получения этих результатов A05 не архивируется и enforcement не объявляется
настроенным. Текущий workflow, UCM и PostgreSQL schema этим change не меняются.
