# Proposal: Защита исходных байтов, секретов и поисковых проекций

## Why
source blobs, SQL literals и будущие search_documents/embeddings потенциально содержат секреты, персональные данные и сведения о приватных репозиториях.

## Goal
Исключить случайное раскрытие секретов через MCP/search и задать политику хранения исходников и производных данных.

## Scope
- Определить уровни данных raw source / evidence / search projection / embedding и правила доступа/retention.
- Разделить сохранение неизменённого оригинала для authorised evidence и redacted поисковый документ.
- Ввести консервативный secret detector с диагностикой и политикой reject/mask/skip без записи plaintext в logs.
- При срабатывании исключать опасные spans из search_documents и embedding input; сохранять provenance/coverage redaction.
- Применять tenant/repository scope ко всем производным данным и аудитам.

## Non-goals
Не изменять оригинальные source blobs, необходимые для доказательств; не обещать находить все секреты regex-сканером.

## Dependencies
A02 для управления доступом; C01 для хранения документов

## Impacted code
src/code_crawler/source_evidence.py; src/code_crawler/search_documents.py; src/code_crawler/server.py; docs/source-evidence.md; docs/search-documents.md; tests/

## Priority
P1 до embeddings

## Acceptance summary
1. Неизменяемость Evidence.
2. Маскирование поисковых данных.
3. Неутечка через диагностику.
4. Доступ и retention.
