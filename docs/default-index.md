# Canonical index by default

`code-crawler index SOURCE` теперь выполняет canonical UCM pipeline: resolve/sync →
registry indexing → exact source archive → validate → atomic publish. Default backend
`ucm`; default Java profile `orm`, dialect `postgres`, naming policy `UNKNOWN`.
Java/Groovy/PLPlus facts читаются опубликованным canonical reader/search/MCP.

```sh
uv run code-crawler index /path/to/repository
uv run code-crawler index git@github.com:org/repository.git --repository-key org/repository
uv run code-crawler index /path/to/repository --java-profile semantic
uv run code-crawler index /path/to/repository --backend legacy
```

Canonical options: `--repository-key`, `--java-profile`, `--dialect`,
`--naming-policy`, `--connections`. По умолчанию repository_key — абсолютный resolved
local path либо remote source identity (URL без credentials/query/fragment). Протоколы
remote URL не объявляются эквивалентными: для переносимого общего ключа используйте
explicit --repository-key. Разные local paths/remote namespaces не объединяются по
basename. Remote clones находятся в REPOS_DIR/name-hash(source identity); origin
существующего clone проверяется перед pull --ff-only, а credentials не входят в key.

Local checkout не pull'ится и не reset'ится; tracked dirty bytes архивируются по
[source-evidence.md](source-evidence.md). Remote clone/update использует существующий
Git wrapper; non-fast-forward/clone failures останавливают команду. Повторный index
переиспользует canonical baseline и создаёт новую атомарную publication. Ingest job
retry работает с сохранённым local checkout path, без дополнительного remote fetch.

index_registered остаётся единственной реализацией adapter/ingest/publication flow;
index всегда передаёт publish=True. `index-sources` сохраняет прежний opt-in --publish
для отдельного BUILDING workflow. Схема БД должна быть актуальной. При parser,
validation, source archive или publication failure возвращается nonzero exit, старый
published pointer сохраняется; автоматического legacy fallback нет.

## Explicit legacy compatibility

`--backend legacy` вызывает прежний writer (Java/PLPlus) и печатает предупреждение:
legacy executes — SQL discovery, не подтверждённое выполнение. Canonical options в
этом режиме отклоняются. Legacy tables/compatibility projection сохраняются для
старых потребителей; legacy executes не переводятся в EXECUTES_SQL/SQL_EXECUTE или
EXECUTES_STATEMENT. Standard index не вызывает legacy writer и не зависит от него.

Для перехода старого индекса используйте `index ... --backend legacy`, затем
`migrate-index`/`compare-index` при необходимости. Обычный canonical index не требует
migration bridge или `use-index`; search/MCP читают canonical publication напрямую.
`use-index` выбирает только backend compatibility reader и не меняет default writer.

Ограничения адаптеров остаются прежними: Java call/SQL profiles fail closed при
parser diagnostics, частичные capabilities явно сохраняются. Выбор более узкого
profile явный и не превращает отсутствующие факты в подтверждённые.
