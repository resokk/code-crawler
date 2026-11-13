# UCM atomic publication

## Проблема и цель

BUILDING facts пока не имеют проверенного пути к публикации. Нужен validation gate для фактического содержимого storage и короткое атомарное переключение pointer с сохранением прежнего индекса при любом сбое.

## Границы

Восстановление UcmBatch из storage, freeze/validation/receipt/READY, compare-and-swap publication и rollback к RETIRED snapshot. Миграция 0005 и интеграционные проверки. Без переключения legacy CLI, retention, incremental indexing, durable ingest telemetry и проверки истинности анализа или исходных bytes.
