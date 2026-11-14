# Proposal: Гибридный exact/FTS/vector/graph поиск

## Why
Есть exact structural и lexical search, но нет согласованного retrieval, который комбинирует идентификаторы, векторы и граф с доказательствами.

## Outcome
Гибридный exact/FTS/vector/graph поиск. Реализовать независимые exact, FTS/trigram, vector candidate producers с общим фильтром repo/snapshot/ACL. Комбинировать результаты через настраиваемую RRF или понятный ranking с traceable component scores. Обогащать top candidates только bounded graph expansion с Evidence, certainty и coverage. Измерять retrieval quality на русском/английском наборе вопросов по schema+SQL+API, фиксировать метрики без выдуманных процентов.

## Scope
- Реализовать независимые exact, FTS/trigram, vector candidate producers с общим фильтром repo/snapshot/ACL.
- Комбинировать результаты через настраиваемую RRF или понятный ranking с traceable component scores.
- Обогащать top candidates только bounded graph expansion с Evidence, certainty и coverage.
- Измерять retrieval quality на русском/английском наборе вопросов по schema+SQL+API, фиксировать метрики без выдуманных процентов.

## Non-goals
Векторное сходство не является evidence доказанного вызова.

## Dependencies
C01,C06,C07

## Impacted code
src/code_crawler/search.py; src/code_crawler/server.py; src/code_crawler/migrations/; tests/integration/; docs/

## Priority
P1
