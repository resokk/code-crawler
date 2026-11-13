# UCM legacy migration

## Проблема и цель

Legacy CLI и данные пока отделены от UCM snapshots. Нужен проверяемый переходный read path, который сохраняет рабочие ответы до появления всех нормативных Java/SQL/PLPlus adapters и позволяет явно переключать чтение.

## Границы

Compatibility projection, envelope converter, миграция существующего индекса, полный comparison, persistent read backend и CLI commands. Legacy tables и команда index сохраняются; default backend legacy. Без удаления legacy, автоматического schema import, законченной SQL execution семантики и MCP query tools. Incremental UCM API остаётся независимым, bridge выполняет полный разбор из captured bytes.
