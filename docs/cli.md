# CLI

`code-crawler` — инструмент управления индексами. Индексы изменяет только он; сервер их только читает.

```bash
uv run code-crawler <команда>
```

| Команда | Что делает |
| --- | --- |
| `db status` | проверяет, что схема БД соответствует коду — см. [db.md](db.md) |
| `db init` | готовит пустую БД и применяет все миграции — см. [db.md](db.md) |
| `db migrate` | применяет недостающие миграции схемы — см. [db.md](db.md) |
| `schema import-version --database-key KEY --version-key VERSION` | независимый immutable PostgreSQL import — см. [database-identity.md](database-identity.md) |
| `schema import-manifest PATH` | импорт typed JSON manifest в versioned inventory |
| `schema import` | читает структуру прикладной БД в слой данных — см. [data-model.md](data-model.md) |
| `adapters list` | описывает built-in versioned Java profiles, Groovy и PL/Plus adapters без доступа к БД |
| `snapshot validate UUID` | проверяет canonical snapshot и переводит его в READY |
| `snapshot publish UUID --expected-current UUID\|none` | validation и атомарная CAS публикация — [контракт](canonical-publication-cli.md) |
| `index-sources ROOT --repository-key KEY [--publish]` | строит canonical BUILDING snapshot; `--publish` проверяет и публикует через существующий lifecycle API — см. [source-adapters.md](source-adapters.md) |
| `index <источник>` | строит или обновляет индекс репозитория — см. [indexing.md](indexing.md) |

`<источник>` — локальный каталог или URL репозитория. Пример:

```bash
uv run code-crawler index git@host:group/billing.git
uv run code-crawler index ~/work/billing
```

Перед индексацией схема БД должна быть актуальной (`db status`). По завершении печатаются имя репозитория, ветка, коммит и число файлов, классов, методов, SQL-запросов и таблиц.

Команд удаления и просмотра индексов пока нет.

## Прогресс и статус

Каждая операция выполняется внутри `operation(title)` из `code_crawler.cli`:

- пока операция идёт, в терминале виден индикатор с названием и прошедшим временем;
- счётные шаги показываются отдельными полосами: `progress.add_task("Файлы", total=n)`, затем `progress.advance(task)`;
- по завершении индикатор исчезает и остаётся строка статуса: `✓ <название>` при успехе или `✗ <название>: <ошибка>` при сбое;
- при сбое процесс завершается с кодом 1.

```python
with operation("Индексация repo") as progress:
    task = progress.add_task("Файлы", total=len(files))
    for file in files:
        ...
        progress.advance(task)
```

Код глубже CLI (адаптеры, анализаторы) сообщает о прогрессе через
`ingestion.tick(stage, total)`: один вызов на обработанный файл, без `total` —
начало несчётного этапа. CLI подписывается через `ingestion.progress.set(callback)`
и заводит полосу на каждый этап. Так `index-sources` показывает каталог и анализ
PL/Plus и Java, анализ Groovy, проверку результатов адаптеров, сборку и перепроверку
снимка, загрузку в БД (по порциям), перенос (по таблицам) и проверку связей
(по ограничениям); без подписчика `tick`
ничего не делает.

Вывод идёт через `rich`; вне терминала (перенаправление в файл, CI) анимация отключается, строка статуса остаётся.

## Переход с legacy на UCM

```bash
uv run code-crawler index ~/work/billing
uv run code-crawler migrate-index billing --repository-key org/billing
uv run code-crawler compare-index org/billing
uv run code-crawler use-index org/billing --backend ucm
uv run code-crawler show-index org/billing
# Возврат чтения без удаления snapshots:
uv run code-crawler use-index org/billing --backend legacy
```

`migrate-index` публикует новый snapshot, сохраняя legacy. `compare-index` выдаёт
полный compatibility report и exit 1 при расхождении. `use-index ucm` требует
совпадения индексов; `show-index` возвращает nodes/edges/refs выбранного reader.
После следующего `index` повторите `migrate-index`, чтобы обновить UCM snapshot.
Точный контракт и ограничения семантики: [ucm-legacy-migration.md](ucm-legacy-migration.md).

Актуальный порядок разработки: [план 2.0](development-plan-v2.md).

Canonical snapshot reports также показывают archive status, archived/source file
counts и commit/fingerprint/dirty. Новые publications требуют exact source bytes;
`index-sources` сохраняет их автоматически, включая dirty worktrees. Generic
producers архивируют bytes до validation: [source-evidence.md](source-evidence.md).
