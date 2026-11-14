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
| `index-sources ROOT --repository-key KEY` | строит canonical BUILDING snapshot через source registry — см. [source-adapters.md](source-adapters.md) |
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
