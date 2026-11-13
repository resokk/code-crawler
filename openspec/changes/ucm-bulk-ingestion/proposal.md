# UCM bulk ingestion

## Проблема и цель

Нормализованные UCM таблицы пока заполняются только SQL fixtures. Нужен единый writer для всех существующих UCM типов, независимый от языковых адаптеров, с проверкой замкнутого batch и атомарным переносом фактов.

## Границы

UcmBatch, локальная cross-reference validation, typed temporary staging/COPY, два прохода канонической загрузки, mapping logical ID к snapshot-scoped physical key и rollback. Без CLI switch, publication, partial-file batches, durable ingest jobs/stages/diagnostics или streaming/resume. Для этих возможностей потребуются отдельные небольшие changes; здесь ошибки возвращаются вызывающему коду.
